################################################################################
# Automatically-generated file. Do not edit!
################################################################################

O_SRCS :=
CPP_SRCS :=
C_UPPER_SRCS :=
C_SRCS :=
S_UPPER_SRCS :=
OBJ_SRCS :=
ASM_SRCS :=
CXX_SRCS :=
C++_SRCS :=
CC_SRCS :=
OBJS :=
C++_DEPS :=
C_DEPS :=
CC_DEPS :=
CPP_DEPS :=
EXECUTABLES :=
CXX_DEPS :=
C_UPPER_DEPS :=

USER_FLAGS :=-DWITH_EXTRA_NEW
#USER_FLAGS += -DPIPE_SLICING
#USER_FLAGS += -DCHECK_REACH_SHADOW
#USER_FLAGS += -DCHECK_SIMPLE_SHADOW
USER_FLAGS += -DCHECK_ANOMALIES
#USER_FLAGS += -DCHECK_BLACKHOLES
#USER_FLAGS += -DNEW_HS
#USER_FLAGS += -DUSE_DEPRECATED
#USER_FLAGS += -DUSE_BDD
USER_FLAGS += -DSTRICT_RW
#USER_FLAGS += DDENSE_LOOPS
#USER_FLAGS += -DGENERIC_PS
#USER_FLAGS += -DSORTED_DIR
#USER_FLAGS += -DSORTED_FWD

#DEBUG_FLAGS =-g
#DEBUG_FLAGS += $(COV_FLAGS)
#DEBUG_FLAGS += -pg

GCFLAGS =-Wall -Wextra -Wpedantic -O3 $(DEBUG_FLAGS) $(USER_FLAGS)

# Every subdirectory with source files must be described here
SUBDIRS := \
src/net_plumber/test \
src/net_plumber \
src/jsoncpp \
src/headerspace/test \
src/headerspace \

