"""
This module provides a central data store and utility functions for thermal analysis calibration data.
The data structure is designed to make lookups efficient while maintaining extensibility.
"""

import json
from dataclasses import dataclass
from typing import Dict, Tuple, Optional

@dataclass
class CalibrationKey:
    """Key class for looking up calibration data"""
    system_name: str
    hbm_stack_height: int
    htc: int
    tim_cond: int
    infill_cond: int
    underfill_cond: int
    dummy_si: bool

    def to_dict(self) -> dict:
        """Convert key to dictionary format for storage"""
        return {
            'system_name': self.system_name,
            'hbm_stack_height': self.hbm_stack_height,
            'htc': self.htc,
            'tim_cond': self.tim_cond,
            'infill_cond': self.infill_cond,
            'underfill_cond': self.underfill_cond,
            'dummy_si': self.dummy_si
        }

    @staticmethod
    def from_dict(d: dict) -> 'CalibrationKey':
        """Create key from dictionary"""
        return CalibrationKey(
            system_name=d['system_name'],
            hbm_stack_height=d['hbm_stack_height'],
            htc=d['htc'],
            tim_cond=d['tim_cond'],
            infill_cond=d['infill_cond'],
            underfill_cond=d['underfill_cond'],
            dummy_si=d['dummy_si']
        )

@dataclass
class CalibrationData:
    """Container for calibration data"""
    gpu_calibration: Dict[float, Tuple[float, float]]  # HBM power -> (slope, intercept)
    hbm_calibration: Dict[float, Tuple[float, float]]  # HBM power -> (slope, intercept)

    def to_dict(self) -> dict:
        """Convert data to dictionary format for storage"""
        return {
            'gpu_calibration': {str(k): v for k, v in self.gpu_calibration.items()},
            'hbm_calibration': {str(k): v for k, v in self.hbm_calibration.items()}
        }

    @staticmethod
    def from_dict(d: dict) -> 'CalibrationData':
        """Create data from dictionary"""
        return CalibrationData(
            gpu_calibration={float(k): tuple(v) for k, v in d['gpu_calibration'].items()},
            hbm_calibration={float(k): tuple(v) for k, v in d['hbm_calibration'].items()}
        )

class ThermalCalibrationStore:
    """Central store for thermal calibration data"""
    def __init__(self, data_file: str = 'dray_ECTC4.json'):
        self.data_file = data_file
        self.calibration_data: Dict[str, CalibrationData] = {}
        self.load_data()

    def get_key_string(self, key: CalibrationKey) -> str:
        """Generate a unique string key from CalibrationKey"""
        return f"{key.system_name}_{key.hbm_stack_height}_{key.htc}_{key.tim_cond}_{key.infill_cond}_{key.underfill_cond}_{key.dummy_si}"

    def add_calibration(self, key: CalibrationKey, data: CalibrationData):
        """Add or update calibration data"""
        key_str = self.get_key_string(key)
        self.calibration_data[key_str] = data
        self.save_data()

    def get_calibration(self, key: CalibrationKey) -> Optional[CalibrationData]:
        """Retrieve calibration data for given parameters"""
        key_str = self.get_key_string(key)
        return self.calibration_data.get(key_str)

    def get_gpu_calibration(self, key: CalibrationKey, hbm_power: float) -> Optional[Tuple[float, float]]:
        """Get GPU calibration for specific configuration and HBM power"""
        data = self.get_calibration(key)
        if data and hbm_power in data.gpu_calibration:
            return data.gpu_calibration[hbm_power]
        return None

    def get_hbm_calibration(self, key: CalibrationKey, hbm_power: float) -> Optional[Tuple[float, float]]:
        """Get HBM calibration for specific configuration and HBM power"""
        data = self.get_calibration(key)
        if data and hbm_power in data.hbm_calibration:
            return data.hbm_calibration[hbm_power]
        return None

    def save_data(self):
        """Save calibration data to JSON file"""
        data_dict = {}
        for key_str, cal_data in self.calibration_data.items():
            data_dict[key_str] = cal_data.to_dict()
        
        with open(self.data_file, 'w') as f:
            json.dump(data_dict, f, indent=2)

    def load_data(self):
        """Load calibration data from JSON file"""
        try:
            with open(self.data_file, 'r') as f:
                data_dict = json.load(f)
            
            self.calibration_data = {
                key_str: CalibrationData.from_dict(data)
                for key_str, data in data_dict.items()
            }
        except FileNotFoundError:
            self.calibration_data = {}

# Example usage:
def migrate_standard_config(store: ThermalCalibrationStore, config: dict):
    """Migrate a standard configuration to the new format"""
    gpu_cal = config.get('gpu_calibration', {})
    hbm_cal = config.get('hbm_calibration', {})
    key = CalibrationKey(**config['key'])
    
    data = CalibrationData(
        gpu_calibration=gpu_cal,
        hbm_calibration=hbm_cal
    )
    store.add_calibration(key, data)

def migrate_from_dray_ECTC3():
    """Utility function to migrate data from dray_ECTC3.txt format"""
    store = ThermalCalibrationStore()
    
    # Standard configurations from ECTC3
    configurations = [
        {
            'key': {
                'system_name': "3D_1GPU",
                'hbm_stack_height': 8,
                'htc': 10,
                'tim_cond': 10,
                'infill_cond': 19,
                'underfill_cond': 19,
                'dummy_si': True
            },
            'gpu_calibration': {
                5.0: (0.134, 48.89),
                5.6: (0.134, 49.37),
                6.8024: (0.134, 50.31)
            },
            'hbm_calibration': {
                5.0: (0.132, 49.18),
                5.6: (0.132, 49.64),
                6.8024: (0.132, 50.49)
            }
        },
        {
            'key': {
                'system_name': "2p5D_1GPU",
                'hbm_stack_height': 8,
                'htc': 10,
                'tim_cond': 10,
                'infill_cond': 19,
                'underfill_cond': 19,
                'dummy_si': False
            },
            'gpu_calibration': {
                5.0: (0.123, 29.88),
                5.6: (0.124, 29.73),
                6.8024: (0.127, 29.41)
            },
            'hbm_calibration': {
                5.0: (0.119, 30.32),
                5.6: (0.120, 30.16),
                6.8024: (0.123, 29.83)
            }
        },
        # 3D_1GPU configurations with TIM_cond=5
        {
            'key': {
                'system_name': "3D_1GPU",
                'hbm_stack_height': 8,
                'htc': 10,
                'tim_cond': 5,
                'infill_cond': 1,
                'underfill_cond': 1,
                'dummy_si': True
            },
            'gpu_calibration': {
                5.0: (0.191, 50.59),
                5.6: (0.191, 51.27),
                6.8024: (0.191, 52.61)
            },
            'hbm_calibration': {
                5.0: (0.190, 50.72),
                5.6: (0.190, 51.43),
                6.8024: (0.191, 52.61)
            }
        },
        {
            'key': {
                'system_name': "3D_1GPU",
                'hbm_stack_height': 8,
                'htc': 10,
                'tim_cond': 5,
                'infill_cond': 1,
                'underfill_cond': 19,
                'dummy_si': True
            },
            'gpu_calibration': {
                5.0: (0.189, 50.58),
                5.6: (0.188, 51.25),
                6.8024: (0.189, 52.55)
            },
            'hbm_calibration': {
                5.0: (0.187, 50.76),
                5.6: (0.187, 51.43),
                6.8024: (0.187, 52.65)
            }
        },
        # 3D_1GPU configurations with TIM_cond=10
        {
            'key': {
                'system_name': "3D_1GPU",
                'hbm_stack_height': 8,
                'htc': 10,
                'tim_cond': 10,
                'infill_cond': 1,
                'underfill_cond': 1,
                'dummy_si': True
            },
            'gpu_calibration': {
                5.0: (0.177, 50.20),
                5.6: (0.177, 50.83),
                6.8024: (0.177, 52.09)
            },
            'hbm_calibration': {
                5.0: (0.176, 50.41),
                5.6: (0.176, 51.05),
                6.8024: (0.176, 52.30)
            }
        },
        {
            'key': {
                'system_name': "3D_1GPU",
                'hbm_stack_height': 8,
                'htc': 10,
                'tim_cond': 10,
                'infill_cond': 1,
                'underfill_cond': 19,
                'dummy_si': True
            },
            'gpu_calibration': {
                5.0: (0.175, 50.15),
                5.6: (0.175, 50.78),
                6.8024: (0.175, 52.02)
            },
            'hbm_calibration': {
                5.0: (0.174, 50.26),
                5.6: (0.174, 50.89),
                6.8024: (0.173, 52.15)
            }
        },
        # 3D_1GPU configurations with TIM_cond=50
        {
            'key': {
                'system_name': "3D_1GPU",
                'hbm_stack_height': 8,
                'htc': 10,
                'tim_cond': 50,
                'infill_cond': 1,
                'underfill_cond': 1,
                'dummy_si': True
            },
            'gpu_calibration': {
                5.0: (0.166, 49.93),
                5.6: (0.166, 50.50),
                6.8024: (0.166, 51.66)
            },
            'hbm_calibration': {
                5.0: (0.164, 50.20),
                5.6: (0.164, 50.77),
                6.8024: (0.165, 51.85)
            }
        },
        {
            'key': {
                'system_name': "3D_1GPU",
                'hbm_stack_height': 8,
                'htc': 10,
                'tim_cond': 50,
                'infill_cond': 1,
                'underfill_cond': 19,
                'dummy_si': True
            },
            'gpu_calibration': {
                5.0: (0.164, 49.88),
                5.6: (0.164, 50.46),
                6.8024: (0.164, 51.61)
            },
            'hbm_calibration': {
                5.0: (0.162, 50.08),
                5.6: (0.162, 50.66),
                6.8024: (0.162, 51.81)
            }
        },
        # 2p5D_1GPU configurations
        {
            'key': {
                'system_name': "2p5D_1GPU",
                'hbm_stack_height': 8,
                'htc': 7,
                'tim_cond': 5,
                'infill_cond': 1,
                'underfill_cond': 1,
                'dummy_si': False
            },
            'gpu_calibration': {
                5.0: (0.175, 32.07),
                5.6: (0.177, 31.98),
                6.8024: (0.180, 31.80)
            },
            'hbm_calibration': {
                5.0: (0.173, 31.83),
                5.6: (0.175, 31.74),
                6.8024: (0.179, 31.55)
            }
        },
        {
            'key': {
                'system_name': "2p5D_1GPU",
                'hbm_stack_height': 8,
                'htc': 7,
                'tim_cond': 10,
                'infill_cond': 1,
                'underfill_cond': 1,
                'dummy_si': False
            },
            'gpu_calibration': {
                5.0: (0.161, 32.99),
                5.6: (0.163, 32.90),
                6.8024: (0.166, 32.74)
            },
            'hbm_calibration': {
                5.0: (0.161, 32.75),
                5.6: (0.163, 32.67),
                6.8024: (0.166, 32.50)
            }
        }
    ]

    # Migrate each configuration
    for config in configurations:
        migrate_standard_config(store, config)

    print("Migration complete! Data saved to dray_ECTC4.json")

if __name__ == '__main__':
    migrate_from_dray_ECTC3()