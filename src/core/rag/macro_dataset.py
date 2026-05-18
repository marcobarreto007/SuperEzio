"""
Macro Dataset Engine
-------------------
Gerencia a ingestão e recuperação de séries históricas macroeconômicas
que alimentam o CrisisMathExpert.
"""

import json
import os
import pandas as pd
from typing import List, Dict, Any, Optional
from datetime import datetime
from core.paths import resolve_project_path


class MacroDataset:
    def __init__(self, data_dir: str = "data/macro_dataset"):
        self.data_dir = str(resolve_project_path(data_dir))
        os.makedirs(self.data_dir, exist_ok=True)
        self.index_path = os.path.join(self.data_dir, "dataset_index.json")
        self._load_index()

    def _load_index(self):
        if os.path.exists(self.index_path):
            with open(self.index_path, "r", encoding="utf-8") as f:
                self.index = json.load(f)
        else:
            self.index = {"series": {}, "last_update": None}

    def _save_index(self):
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self.index, f, indent=2)

    def add_series(self, name: str, country: str, df: pd.DataFrame, metadata: dict = None):
        """
        Adiciona uma série ao dataset gigante.
        df deve ter 'date' e o valor da série.
        """
        filename = f"{country.lower()}_{name.lower()}.parquet"
        filepath = os.path.join(self.data_dir, filename)

        # Salva em Parquet (eficiente para 'dataset gigante')
        df.to_parquet(filepath, index=False)

        self.index["series"][f"{country}_{name}"] = {
            "name": name,
            "country": country,
            "file": filename,
            "last_date": str(df["date"].max()),
            "count": len(df),
            "metadata": metadata or {},
        }
        self.index["last_update"] = datetime.now().isoformat()
        self._save_index()

    def get_series(self, name: str, country: str) -> Optional[pd.DataFrame]:
        key = f"{country}_{name}"
        if key not in self.index["series"]:
            return None

        filepath = os.path.join(self.data_dir, self.index["series"][key]["file"])
        return pd.read_parquet(filepath)

    def query_context(self, country: str, top_n: int = 12) -> List[Dict[str, Any]]:
        """
        Retorna um dicionário formatado para o CrisisInput com as últimas observações.
        """
        relevant_series = [
            s for k, s in self.index["series"].items() if s["country"].lower() == country.lower()
        ]

        master_df = None
        for s_info in relevant_series:
            df = self.get_series(s_info["name"], s_info["country"])
            if df is not None:
                df = df.sort_values("date")
                if master_df is None:
                    master_df = df
                else:
                    master_df = pd.merge(master_df, df, on="date", how="outer")

        if master_df is not None:
            return master_df.sort_values("date").tail(top_n).to_dict(orient="records")
        return []


macro_engine = MacroDataset()
