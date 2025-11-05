import pandas as pd 
import numpy as np 
import json 
import config
from datetime import datetime, timedelta


class ScorecardGenerator: 
    def __init__(self, df: pd.DataFrame, output_path: str, config: dict): 
        self.df = df 
        self.config = config 
        self.output_path = output_path 
        self._validate_config() 
        self._preprocess_df()

    def _validate_config(self):
        for col in ["col_responsavel", "col_origem", "col_data_contato", "col_data_cadastro", "col_data_conversao", "col_status"]:
            if col not in self.config:
                raise ValueError(f"Configuração faltando: {col}")
        if "metas_contato_por_canal" not in self.config:
            raise ValueError("Configuração faltando: metas_contato_por_canal")
        if "metas_semanais_gerais" not in self.config:
            raise ValueError("Configuração faltando: metas_semanais_gerais")

    def _preprocess_df(self):
        self.df = self.df.rename(columns={
            self.config["col_responsavel"]: "responsavel",
            self.config["col_lead"]: "name",
            self.config["col_origem"]: "origem",
            self.config["col_data_contato"]: "data_contato",
            self.config["col_data_cadastro"]: "data_cadastro",
            self.config["col_data_conversao"]: "data_conversao",
            self.config["col_status"]: "Status"
        })
        for col in ["data_contato", "data_cadastro", "data_conversao"]:
            self.df[col] = pd.to_datetime(self.df[col], errors='coerce')
        self.df["origem"] = self.df["origem"].astype(str)
        self.df.dropna(subset=["data_contato"], inplace=True)
        if 'id' not in self.df.columns:
            self.df['id'] = self.df.index
        self.df["responsavel"] = self.df["responsavel"].map(config.ADES_SCOUTING).fillna("Desligado")

    def _calculate_period(self):
        if self.df.empty:
            return None, None, 0
        start = self.df["data_contato"].min()
        end = self.df["data_contato"].max()
        num_days = (end - start).days + 1
        num_weeks = np.ceil(num_days / 7)
        
        return num_days, num_weeks, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), start, end

    def _calculate_individual_num_weeks(self, start_date_responsavel, end_date_report):
        effective_start = max(start_date_responsavel, self.df["data_contato"].min())
        if effective_start > end_date_report:
            return 0
        num_days_active = (end_date_report - effective_start).days + 1
        num_weeks_individual = np.ceil(num_days_active / 7)
        
        return max(num_weeks_individual, 1)

    def _calculate_volume_score_contatos(self, row, num_weeks):
        metas = self.config["metas_contato_por_canal"]
        pesos = self.config["pesos_contatos_por_origem"]
        ating = []
        for canal, meta in metas.items():
            atingido = row.get(f"contatos_origem_{canal}", 0)
            ating.append(min(atingido / (meta * num_weeks) if meta else 1, 1))
        volume_pond = sum(row.get(f"contatos_origem_{c}", 0) * p for c, p in pesos.items())
        max_vol = sum(metas.values()) * num_weeks * max(pesos.values()) if pesos else 1
        qualidade = volume_pond / max_vol if max_vol else 0
        
        return round((0.6 * np.mean(ating) + 0.4 * qualidade), 2)

    def _calculate_volume_score_cadastros(self, row, num_weeks):
        # Meta fixa de 2 cadastros por semana independente da origem
        meta_total = 2 * num_weeks
        cadastros_total = row.get("cadastros", 0)
        # Percentual atingido limitado a 1
        atingimento = min(cadastros_total / meta_total if meta_total else 1, 1)
        
        return round(atingimento, 2)

    def _calculate_velocidade_score(self, row):
        score_vel = 0
        if pd.notna(row["data_cadastro"]) and pd.notna(row["data_contato"]):
            dias = (row["data_cadastro"] - row["data_contato"]).days
            if dias <= 3: score_vel = 1
            elif dias >= 15: score_vel = 0.2
            else: score_vel = max(0, (3 - dias) / 15)
        score_qual = 0
        if pd.notna(row["data_cadastro"]) and pd.notna(row["data_conversao"]):
            dias = (row["data_conversao"] - row["data_cadastro"]).days
            if dias <= 2: score_qual = 1
            elif dias >= 5: score_qual = 0.5
            else: score_qual = max(0, (5 - dias) / 5)
            
        velocidade = max(0, min(score_vel * 0.8 + score_qual * 0.2, 1))
        if np.isnan(velocidade):
            return 0
        
        return velocidade

    def _calculate_consistencia(self, daily_series):
        weekly = daily_series.resample('W').sum()
        media = weekly.mean()
        desvio = weekly.std()
        if media == 0: return 0
        consistencia = max(0, min(1, 1 - (desvio / media)))
        
        return round(consistencia,2)

    def _calculate_distribuicao(self, contatos_por_origem):
        metas = self.config["metas_contato_por_canal"]
        total = sum(contatos_por_origem.values())
        if total == 0: return 0
        p_real = {k: v / total for k, v in contatos_por_origem.items()}
        total_meta = sum(metas.values())
        p_ideal = {k: metas[k] / total_meta for k in metas}
        diff = sum(abs(p_real.get(k,0) - p_ideal.get(k,0)) for k in metas)
        
        return round(max(0, min(1, 1 - diff / 2)), 2)

    def _calculate_score_final(self, volume_cad, volume_cont, velocidade, consistencia, distribuicao):
        return round((
            volume_cad * 0.60 +
            volume_cont * 0.15 +
            velocidade * 0.10 +
            consistencia * 0.10 +
            distribuicao * 0.05
        ), 2)
        
    def _calculate_score_geral(geral_data, pesos):
        return round((
            
        ), 2)

    def generate_scorecard(self):
        
        def convert_np(obj):
            import numpy as np
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return float(obj)
            if isinstance(obj, (np.ndarray,)):
                return obj.tolist()
            return str(obj)


        num_days_total, num_weeks_total, period_start, period_end, period_start_dt, period_end_dt = self._calculate_period()
        summary_data = []
        for _, row in self.df.iterrows():
            summary_data.append({
                "id": row["id"],
                "lead": row["name"],
                "responsavel": row["responsavel"],
                "origem": row["origem"],
                "data_contato": row["data_contato"].strftime("%Y-%m-%d") if pd.notna(row["data_contato"]) else None,
                "data_cadastro": row["data_cadastro"].strftime("%Y-%m-%d") if pd.notna(row["data_cadastro"]) else None,
                "data_conversao": row["data_conversao"].strftime("%Y-%m-%d") if pd.notna(row["data_conversao"]) else None,
                "status": row["Status"]
            })

        per_responsavel_data = []
        for responsavel, group in self.df.groupby('responsavel'):
            contatos = len(group)
            cadastros = group["data_cadastro"].count()
            conversoes = group["data_conversao"].count()
            first_date = group["data_contato"].min()
            num_weeks_individual = self._calculate_individual_num_weeks(first_date, period_end_dt)
            contatos_por_origem = group.groupby('origem')['data_contato'].count().to_dict()
            cadastros_por_origem = group.groupby('origem')['data_cadastro'].count().to_dict()
            row_agg = {
                "responsavel": responsavel,
                "contatos": contatos,
                "cadastros": cadastros,
                "conversoes": conversoes,
                "taxa_conversao": round((conversoes / cadastros * 100), 2) if cadastros > 0 else 0,
                "taxa_cadastro": round((cadastros / contatos * 100), 2) if contatos > 0 else 0,
            }
            for canal in self.config["metas_contato_por_canal"].keys():
                row_agg[f"contatos_origem_{canal}"] = contatos_por_origem.get(canal, 0)
                row_agg[f"cadastros_origem_{canal}"] = cadastros_por_origem.get(canal, 0)
            vol_cont = self._calculate_volume_score_contatos(row_agg, num_weeks_individual)
            vol_cad = self._calculate_volume_score_cadastros(row_agg, num_weeks_individual)
            vel_scores = group.apply(self._calculate_velocidade_score, axis=1)
            velocidade = vel_scores[pd.notna(group["data_cadastro"])].mean() if not vel_scores.empty else 0
            if np.isnan(velocidade): velocidade = 0
            consistencia = self._calculate_consistencia(group.set_index('data_contato')['id'])
            distribuicao = self._calculate_distribuicao(contatos_por_origem)
            row_agg["volume_score_contatos"] = vol_cont
            row_agg["volume_score_cadastros"] = vol_cad
            row_agg["velocidade_score"] = round(velocidade, 2)
            row_agg["consistencia"] = consistencia
            row_agg["distribuicao_canais"] = distribuicao
            row_agg["score_final"] = self._calculate_score_final(vol_cad, vol_cont, velocidade, consistencia, distribuicao)
        
            per_responsavel_data.append(row_agg)  
            
        per_responsavel_data = [item for item in per_responsavel_data if item.get("responsavel") != "Desligado"]

        geral_data = []
        for origem, group in self.df.groupby('origem'):
            contatos = len(group)
            cadastros = group["data_cadastro"].count()
            conversoes = group["data_conversao"].count()
            first_date = group["data_contato"].min()
            num_weeks_individual = self._calculate_individual_num_weeks(first_date, period_end_dt)
            row_agg = {
                "origem": origem,
                "contatos": contatos,
                "cadastros": cadastros,
                "conversoes": conversoes,
                "taxa_conversao": round((conversoes / cadastros * 100), 2) if cadastros > 0 else 0,
                "taxa_cadastro": round((cadastros / contatos * 100), 2) if contatos > 0 else 0,
            }
            vol_cont = self._calculate_volume_score_contatos(row_agg, num_weeks_individual)
            vol_cad = self._calculate_volume_score_cadastros(row_agg, num_weeks_individual)
            vel_scores = group.apply(self._calculate_velocidade_score, axis=1)
            velocidade = vel_scores[pd.notna(group["data_cadastro"])].mean() if not vel_scores.empty else 0
            consistencia = self._calculate_consistencia(group.set_index('data_contato')['id'])
            distribuicao = self._calculate_distribuicao({origem: row_agg["contatos"]})
            row_agg["volume_score_contatos"] = vol_cont
            row_agg["volume_score_cadastros"] = vol_cad
            row_agg["velocidade_score"] = round(velocidade, 2)
            row_agg["consistencia"] = consistencia
            row_agg["distribuicao_canais"] = distribuicao
            row_agg["score_final"] = self._calculate_score_final(vol_cad, vol_cont, velocidade, consistencia, distribuicao)
            
            geral_data.append(row_agg)
        
        daily_data = self.df.groupby(self.df["data_contato"].dt.date).agg(
            contatos=("id", "size"),
            cadastros=("data_cadastro", 'count'),
            conversoes=("data_conversao", 'count')
        ).reset_index()
        daily_data_list = daily_data.to_dict(orient='records')

        metas_gerais_periodo = {k: v * num_weeks_total for k, v in self.config["metas_semanais_gerais"].items()}
        total_contatos_geral = self.df["id"].count()
        total_cadastros_geral = self.df["data_cadastro"].count()
        total_conversoes_geral = self.df["data_conversao"].count()
        atingimento_metas_gerais = {
            "contatos": {
                "meta": metas_gerais_periodo.get("contatos", 0),
                "atingido": total_contatos_geral,
                "percentual": (total_contatos_geral / metas_gerais_periodo.get("contatos", 1)) * 100
            },
            "cadastros": {
                "meta": metas_gerais_periodo.get("cadastros", 0),
                "atingido": total_cadastros_geral,
                "percentual": (total_cadastros_geral / metas_gerais_periodo.get("cadastros", 1)) * 100
            },
            "conversoes": {
                "meta": metas_gerais_periodo.get("conversoes", 0),
                "atingido": total_conversoes_geral,
                "percentual": (total_conversoes_geral / metas_gerais_periodo.get("conversoes", 1)) * 100
            }
        }
        # Score geral
        
        atingimento_metas_gerais['metricas_gerais'] = geral_data
        score_geral = []
        for item in geral_data:
            score_geral.append(item["score_final"])
        
        atingimento_metas_gerais['scorecard_geral'] = np.mean(score_geral)

        json_scorecard = {
            "period_info": {
                "start_date": period_start,
                "end_date": period_end,
                "num_weeks_total": num_weeks_total,
                "num_days_total": num_days_total
            },
            "metas_gerais": metas_gerais_periodo,
            "atingimento_metas_gerais": atingimento_metas_gerais,
            "per_responsavel": per_responsavel_data,
            "summary": summary_data,
            "daily_data": daily_data_list
        }

        with open(self.output_path, 'w', encoding='utf-8') as f:
            json.dump(json_scorecard, f, ensure_ascii=False, indent=4, default=convert_np)
        print(f"Arquivo JSON gerado com sucesso em '{self.output_path}'.")