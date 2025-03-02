from ok import Logger
from ok.interaction.BaseInteraction import BaseInteraction

logger = Logger.get_logger(__name__)


class DoNothingInteraction(BaseInteraction):
    pass
