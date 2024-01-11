import pytest


@pytest.fixture
def sentinel_files():
    return [
        "/tmp/pymp-2b5gr07m/162f8f7e-c954-4f69-bb53-ed820aa6432a/S2A_MSIL2A_20231007T100031_N0509_R122_T32TQM_20231007T142901.SAFE/GRANULE/L2A_T32TQM_A043305_20231007T100026/IMG_DATA/R20m/T32TQM_20231007T100031_B01_20m.jp2",
        "/tmp/pymp-2b5gr07m/162f8f7e-c954-4f69-bb53-ed820aa6432a/S2A_MSIL2A_20231007T100031_N0509_R122_T32TQM_20231007T142901.SAFE/GRANULE/L2A_T32TQM_A043305_20231007T100026/IMG_DATA/R20m/T32TQM_20231007T100031_B10_20m.jp2",
        "/tmp/pymp-2b5gr07m/162f8f7e-c954-4f69-bb53-ed820aa6432a/S2A_MSIL2A_20231007T100031_N0509_R122_T32TQM_20231007T142901.SAFE/GRANULE/L2A_T32TQM_A043305_20231007T100026/IMG_DATA/R30m/T32TQM_20231007T100031_B04_30m.jp2",
        "/tmp/pymp-2b5gr07m/162f8f7e-c954-4f69-bb53-ed820aa6432a/S2A_MSIL2A_20231007T100031_N0509_R122_T32TQM_20231007T142901.SAFE/GRANULE/L2A_T32TQM_A043305_20231007T100026/IMG_DATA/R10m/T32TQM_20231007T100031_B12_40m.jp2",
    ]
