import argparse

from dataclasses import dataclass


@dataclass
class LSLConfig:
    stream_name: str
    columns: list[str]


def parse_lsl_config(value):

    # Return matching preset
    if value in LSL_STREAMS:
        return LSLConfig(
            stream_name=value,
            columns=LSL_STREAMS[value],
        )

    raise argparse.ArgumentTypeError(
        f"Unknown LSL stream '{value}'. "
        f"Add it to the config or choose one of: {', '.join(LSL_STREAMS.keys())}"
    )


LSL_STREAMS = {
    "MendiLSL": [
        "acc_x", "acc_y", "acc_z",
        "ang_x", "ang_y", "ang_z",
        "temp",
        "ir_l", "red_l", "amb_l",
        "ir_r", "red_r", "amb_r",
        "ir_p", "red_p", "amb_p",
        "battery_voltage", "timestamp"
    ],
    "OxySoft": [
        "rx1_l1", "rx1_l2", "rx1_l3", "rx1_l4",
        "rx1_l5", "rx1_l6", "rx1_l7", "rx1_l8",
        "rx1_l9", "rx1_l10", "rx1_l11", "rx1_l12",
        "rx1_l13", "rx1_l14", "rx1_l15", "rx1_l16",
        "rx2_l1", "rx2_l2", "rx2_l3", "rx2_l4",
        "rx2_l5", "rx2_l6", "rx2_l7", "rx2_l8",
        "rx2_l9", "rx2_l10", "rx2_l11", "rx2_l12",
        "rx2_l13", "rx2_l14", "rx2_l15", "rx2_l16",
        "battery_voltage", "timestamp"
    ]
}
