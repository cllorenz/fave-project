import logging

PT_LOGGER = logging.getLogger("PolicyTranslator")
PT_LOGGER.addHandler(logging.StreamHandler())
PT_LOGGER.setLevel(logging.INFO)
