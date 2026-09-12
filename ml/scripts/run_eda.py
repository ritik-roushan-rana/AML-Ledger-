"""python -m ml.scripts.run_eda  -> outputs/eda_summary.json + outputs/figures/*.png"""
from ml import data, eda

df = data.clean(data.load_raw())
eda.run(df)
