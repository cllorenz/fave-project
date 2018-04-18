################################################################################
# Automatically-generated file. Do not edit!
################################################################################

# Add inputs and outputs from these tool invocations to the build variables
CC_SRCS += \
../src/headerspace/test/array_unit.cc \
../src/headerspace/test/hs_unit.cc

OBJS += \
./src/headerspace/test/array_unit.o \
./src/headerspace/test/hs_unit.o

CC_DEPS += \
./src/headerspace/test/array_unit.d \
./src/headerspace/test/hs_unit.d


# Each subdirectory must supply rules for building sources it contributes
src/headerspace/test/%.o: ../src/headerspace/test/%.cc
	@echo 'Building file: $<'
	@echo 'Invoking: GCC C++ Compiler'
	g++ -g -DJSON_IS_AMALGAMATION -I/usr/include/ -O3 -Wall -c -fmessage-length=0 -MMD -MP -MF"$(@:%.o=%.d)" -MT"$(@:%.o=%.d)" -o "$@" "$<"
	@echo 'Finished building: $<'
	@echo ' '
