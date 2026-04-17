# /seu_projeto/utils/formatters.py

from datetime import datetime
import pandas as pd
from typing import Union

def format_date_to_str(date_val: Union[str, datetime, pd.Timestamp, None]) -> str:
    """
    Converte um valor de data para o formato YYYY/MM/DD.
    Retorna 'TBC' (To Be Confirmed) se a data for nula ou inválida.

    Args:
        date_val: O valor da data a ser formatado.

    Returns:
        A data formatada como string ou 'TBC'.
    """
    if pd.isna(date_val):
        return "TBC"
    try:
        # Se já for datetime ou timestamp, apenas formate
        if isinstance(date_val, (datetime, pd.Timestamp)):
            return date_val.strftime("%Y/%m/%d")
        
        # Se for string, tente alguns formatos comuns
        if isinstance(date_val, str):
            # Tenta converter de vários formatos possíveis
            for fmt in ["%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"]:
                try:
                    return datetime.strptime(date_val, fmt).strftime("%Y/%m/%d")
                except (ValueError, TypeError):
                    continue
            # Se nenhum formato funcionar, retorne a string original
            return date_val
            
        return "TBC"
    except (ValueError, TypeError):
        return "TBC"