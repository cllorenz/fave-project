################################################################################
# Automatically-generated file. Do not edit!
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
DOCS_SRCS += \
../docs/net_plumber.md

DOCS_OBJS += \
./docs/net_plumber.pdf

DOCS_DEPS += \
./docs/net_plumber.d

# Each subdirectory must supply rules for building sources it contributes
docs/%.pdf: ../docs/%.md
	@echo 'Building file: $<'
	@echo 'Invoking: pandoc Compiler'
	pandoc $(GCFLAGS) -o "$@" "$<"
	@echo 'Finished building: $<'
	@echo ' '

