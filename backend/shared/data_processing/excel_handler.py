# /seu_projeto/data_processing/excel_handler.py

import pandas as pd
import xlwings as xw
from typing import Dict, List

class ExcelHandler:
    """
    Gerencia a interação com arquivos Excel, incluindo a execução de macros
    e o carregamento de abas em DataFrames.
    """
    def __init__(self, file_path: str):
        """
        Inicializa o handler com o caminho para o arquivo Excel.

        Args:
            file_path (str): O caminho completo para o arquivo .xlsm.
        """
        if not file_path:
            raise ValueError("O caminho do arquivo Excel não pode ser nulo.")
        self.file_path = file_path
        self.app = None

    def __enter__(self):
        """Inicia a aplicação Excel ao entrar no bloco 'with'."""
        self.app = xw.App(visible=False, add_book=False)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Garante que a aplicação Excel seja fechada ao sair do bloco 'with'."""
        if self.app:
            self.app.quit()

    def refresh_and_load_sheets(
        self,
        sheets_to_load: List[str],
        macro_name: str,
        timeout: int
    ) -> Dict[str, pd.DataFrame]:
        """
        Executa uma macro para atualizar dados e carrega abas específicas em DataFrames.

        Args:
            sheets_to_load (List[str]): Nomes das abas a serem carregadas.
            macro_name (str): Nome da macro VBA a ser executada.
            timeout (int): Tempo máximo de espera para a macro.

        Returns:
            Um dicionário com nomes de abas como chaves e DataFrames como valores.
        """
        print(f"Abrindo e atualizando o arquivo: {self.file_path}...")
        
        try:
            self.app.api.AutomationSecurity = 1  # Habilita a execução de macros
        except AttributeError:
            print("Aviso: Não foi possível definir AutomationSecurity (pode não ser necessário).")

        try:
            wb = self.app.books.open(self.file_path)
            
            print(f"Executando macro '{macro_name}'...")
            vba_macro = wb.macro(macro_name)
            vba_macro(timeout, False)  # Executa a macro (close_after=False)

            dataframes: Dict[str, pd.DataFrame] = {}
            for sheet_name in sheets_to_load:
                try:
                    print(f"Carregando aba: '{sheet_name}'...")
                    sheet = wb.sheets[sheet_name]
                    # Usar a opção de DataFrame do xlwings é mais robusto
                    df = sheet.used_range.options(pd.DataFrame, header=1, index=False).value
                    df.columns = [str(col).strip() for col in df.columns] # Limpa nomes de colunas
                    dataframes[sheet_name] = df
                    print(f" -> Aba '{sheet_name}' carregada com {df.shape[0]} linhas.")
                except Exception as e:
                    print(f"⚠ Erro ao carregar a aba '{sheet_name}': {e}. Pulando.")
                    dataframes[sheet_name] = pd.DataFrame() # Retorna DF vazio em caso de erro

            return dataframes

        except Exception as e:
            raise RuntimeError(f"Falha crítica durante o processamento do Excel: {e}") from e
        finally:
            if 'wb' in locals() and wb:
                wb.close()