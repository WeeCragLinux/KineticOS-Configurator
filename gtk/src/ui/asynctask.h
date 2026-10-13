#pragma once

#include <glibmm/dispatcher.h>

#include <functional>
#include <mutex>
#include <thread>
#include <utility>

namespace kineticos {

// Runs work on a worker thread and delivers the result on the main thread through a
// Glib::Dispatcher. Long file, image or process work must never block the main loop.
template <typename Result>
class AsyncTask final {
public:
    AsyncTask() = default;
    ~AsyncTask() { join(); }

    AsyncTask(const AsyncTask &) = delete;
    AsyncTask &operator=(const AsyncTask &) = delete;

    void start(std::function<Result()> work, std::function<void(Result)> done)
    {
        join();
        m_done = std::move(done);
        m_dispatcher.connect([this] { deliver(); });
        m_thread = std::thread([this, work = std::move(work)] {
            Result result = work();
            {
                const std::lock_guard<std::mutex> lock(m_mutex);
                m_result = std::move(result);
            }
            m_dispatcher.emit();
        });
    }

private:
    void join()
    {
        if (m_thread.joinable())
            m_thread.join();
    }

    void deliver()
    {
        Result result;
        {
            const std::lock_guard<std::mutex> lock(m_mutex);
            result = m_result;
        }
        if (m_done)
            m_done(std::move(result));
    }

    Glib::Dispatcher m_dispatcher;
    std::thread m_thread;
    std::mutex m_mutex;
    Result m_result{};
    std::function<void(Result)> m_done;
};

} // namespace kineticos
