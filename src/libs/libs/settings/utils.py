from libs.common.enums import EnvironmentEnum


def is_stand_env(environment: EnvironmentEnum) -> bool:
    return environment in {EnvironmentEnum.TEST, EnvironmentEnum.PROD}


def is_data_sensitive_env(environment: EnvironmentEnum) -> bool:
    return environment == EnvironmentEnum.PROD
