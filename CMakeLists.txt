cmake_minimum_required(VERSION 3.20)

# Builds the GTK 4 application, which lives in gtk/. The earlier Python configurator in
# source/ is kept for reference only and is not built.
project(kinetic-configurator LANGUAGES C CXX)

include(CTest)

# Put the binary at the top of the build directory (build/kinetic-configurator).
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})

add_subdirectory(gtk)
