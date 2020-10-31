################################################################################
# Automatically-generated file. Do not edit!
################################################################################

-include ../makefile.init

RM := rm -rf

# All of the sources participating in the build are defined here
-include sources.mk
-include src/net_plumber/test/subdir.mk
-include src/net_plumber/subdir.mk
-include src/jsoncpp/subdir.mk
-include src/headerspace/test/subdir.mk
-include src/headerspace/subdir.mk
-include subdir.mk
-include objects.mk
#-include docs.mk
#-include docs/subdir.mk

# All Target
all: net_plumber

MAKECMDGOALS := $(MAKECMDGOALS)
ifeq ($(MAKECMDGOALS),coverage)
	COV_FLAGS :=-fprofile-arcs -ftest-coverage
	LIBS += -lgcov
else
	COV_FLAGS :=
endif

ifneq ($(MAKECMDGOALS),clean)
ifneq ($(strip $(C++_DEPS)),)
-include $(C++_DEPS)
endif
ifneq ($(strip $(C_DEPS)),)
-include $(C_DEPS)
endif
ifneq ($(strip $(CC_DEPS)),)
-include $(CC_DEPS)
endif
ifneq ($(strip $(CPP_DEPS)),)
-include $(CPP_DEPS)
endif
ifneq ($(strip $(CXX_DEPS)),)
-include $(CXX_DEPS)
endif
ifneq ($(strip $(C_UPPER_DEPS)),)
-include $(C_UPPER_DEPS)
endif
ifneq ($(strip $(DOCS_DEPS)),)
-include $(DOCS_DEPS)
endif
endif

-include ../makefile.defs

# Add inputs and outputs from these tool invocations to the build variables

# Tool invocations
net_plumber: $(OBJS) $(USER_OBJS)
	@echo 'Building target: $@'
	@echo 'Invoking: GCC C++ Linker'
	g++ $(GCFLAGS) -o "net_plumber" $(OBJS) $(USER_OBJS) $(LIBS)
	@echo 'Finished building target: $@'
	@echo ' '

# Other Targets
clean:
	-$(RM) $(OBJS)$(C++_DEPS)$(C_DEPS)$(CC_DEPS)$(CPP_DEPS)$(EXECUTABLES)$(CXX_DEPS)$(C_UPPER_DEPS) net_plumber
	-find ../ -name "*.gcov" -delete
	-find ../ -name "*.gcno" -delete
	-find ../ -name "*.gcda" -delete
	-$(RM) net_plumber_coverage.info /tmp/net_plumber_coverage/
	-$(RM) $(DOCS_OBJS)
	-@echo ' '

test: all
	./net_plumber --test

docs: $(DOCS_OBJS)
	-@echo 'Built documentation.'

coverage: all
	./net_plumber --test
	gcov -o ./src/net_plumber/ ../src/net_plumber/main.cc
	lcov --base-directory ../src --directory src/ --capture --output-file net_plumber_coverage.info
	genhtml -o /tmp/net_plumber_coverage/ net_plumber_coverage.info

install: all
	-cp net_plumber /usr/bin/

uninstall:
	-rm -f /usr/bin/net_plumber

buddy_test: ../src/net_plumber/test/buddy_test.cpp
	g++ -o $@ $< -lbdd
	./$@

.PHONY: all clean dependents install uninstall coverage test
.SECONDARY:

-include ../makefile.targets
