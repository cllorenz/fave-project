import logging

PT_LOGGER = logging.getLogger("PolicyTranslator")
PT_LOGGER.addHandler(logging.StreamHandler())
PT_LOGGER.setLevel(logging.INFO)

# add custom trace logging method
TRACE_LEVEL_NUM = 9
logging.addLevelName(TRACE_LEVEL_NUM, 'TRACE')
logging.TRACE = TRACE_LEVEL_NUM
logging.__all__ += ['TRACE']

def trace(self, message, *args, **kws):
    if self.isEnabledFor(TRACE_LEVEL_NUM):
        self._log(TRACE_LEVEL_NUM, message, args, **kws)

logging.Logger.trace = trace
