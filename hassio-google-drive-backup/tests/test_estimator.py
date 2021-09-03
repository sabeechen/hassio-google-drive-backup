import pytest
from backup.util import Estimator
from backup.config import Config, Setting


@pytest.mark.asyncio
async def test_check_space(estimator: Estimator, coord, config: Config):
    estimator.refresh()
    estimator.checkSpace(coord.backups())

    config.override(Setting.LOW_SPACE_THRESHOLD, estimator.getBytesFree() + 1)
    estimator.checkSpace(coord.backups())
