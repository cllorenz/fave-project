################################################################################
# Automatically-generated file. Do not edit!
################################################################################

# Add inputs and outputs from these tool invocations to the build variables
CC_SRCS += \
../src/net_plumber/test/conditions_unit.cc \
../src/net_plumber/test/net_plumber_basic_unit.cc \
../src/net_plumber/test/net_plumber_anomalies_unit.cc \
../src/net_plumber/test/net_plumber_plumbing_unit.cc \
../src/net_plumber/test/net_plumber_slicing_unit.cc \
../src/net_plumber/test/packet_set_unit.cc

OBJS += \
./src/net_plumber/test/conditions_unit.o \
./src/net_plumber/test/net_plumber_basic_unit.o \
./src/net_plumber/test/net_plumber_anomalies_unit.o \
./src/net_plumber/test/net_plumber_plumbing_unit.o \
./src/net_plumber/test/net_plumber_slicing_unit.o \
./src/net_plumber/test/packet_set_unit.o

CC_DEPS += \
./src/net_plumber/test/conditions_unit.d \
./src/net_plumber/test/net_plumber_basic_unit.d \
./src/net_plumber/test/net_plumber_anomalies_unit.d \
./src/net_plumber/test/net_plumber_plumbing_unit.d \
./src/net_plumber/test/net_plumber_slicing_unit.d \
./src/net_plumber/test/packet_set_unit.d


# Each subdirectory must supply rules for building sources it contributes
src/net_plumber/test/%.o: ../src/net_plumber/test/%.cc
	@echo 'Building file: $<'
	@echo 'Invoking: GCC C++ Compiler'
	g++ -DJSON_IS_AMALGAMATION -I/usr/include/ $(GCFLAGS) -std=c++17 -c -fmessage-length=0 -MMD -MP -MF"$(@:%.o=%.d)" -MT"$(@:%.o=%.d)" -o "$@" "$<"
	@echo 'Finished building: $<'
	@echo ' '


