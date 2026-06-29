cmake_minimum_required(VERSION 3.16)
project(PathOfBuildingLauncher CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_executable(PathOfBuilding-PoE2 pob_launcher.cpp)

if (WIN32)
	target_compile_definitions(PathOfBuilding-PoE2 PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)
else()
	target_link_libraries(PathOfBuilding-PoE2 PRIVATE ${CMAKE_DL_LIBS})
endif()

install(TARGETS PathOfBuilding-PoE2 RUNTIME DESTINATION ".")
