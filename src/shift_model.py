import pandas as pd
from ortools.sat.python import cp_model
import datetime
# import os # osはoutput_utilsに移動

from .output_utils import save_results_to_csv # 相対インポート

# 定数定義
EMPLOYEE_FILEPATH = "input/employees.csv" # プロジェクトルートからの相対パス
SHIFTS = ["日勤", "公休", "夜勤", "早出", "明勤"]
# system_requirements.md や shift_20250410_v105.csv の例から判断できる2025年4月・5月の祝日（仮）
HOLIDAYS_2025_APR_MAY = [
    datetime.date(2025, 4, 29), # 昭和の日
    datetime.date(2025, 5, 3),  # 憲法記念日
    datetime.date(2025, 5, 4),  # みどりの日
    datetime.date(2025, 5, 5),  # こどもの日
    datetime.date(2025, 5, 6),  # 振替休日
]
# 個人集計の対象となるシフト（「集計:祝日」は別途対応するためここでは含めないか、含めてもロジックで0にする）
SHIFTS_FOR_AGGREGATION = ["公休", "日勤", "早出", "夜勤", "明勤"]
# 日付別合計の対象となる稼働シフト
WORKING_SHIFTS_FOR_DAILY_TOTAL = ["日勤", "早出", "夜勤", "明勤"]

START_DATE_STR = "2025-04-10"
END_DATE_STR = "2025-05-07"
# OUTPUT_DIR と FILENAME_PREFIX は output_utils に移動

def load_employee_data(filepath: str) -> pd.DataFrame | None:
    """
    従業員情報CSVファイルを読み込み、必要な列（職員ID, 職員名, 担当フロア, 常勤/パート）を
    含むDataFrameを返します。
    エラーが発生した場合はNoneを返します。
    """
    try:
        employees_df = pd.read_csv(filepath)
        # 必要な列が存在するか確認
        required_columns = ["職員ID", "職員名", "担当フロア", "常勤/パート"]
        missing_cols = [col for col in required_columns if col not in employees_df.columns]
        if missing_cols:
            print(f"エラー: {filepath} に必要な列が見つかりません: {', '.join(missing_cols)}")
            return None
        return employees_df
    except FileNotFoundError:
        print(f"エラー: {filepath} が見つかりません。")
        return None
    except Exception as e: # より一般的なエラーキャッチ
        print(f"エラー: {filepath} の読み込み中に予期せぬエラーが発生しました: {e}")
        return None

def generate_date_range(start_date_str: str, end_date_str: str) -> tuple[list[datetime.date], int] | None:
    """
    開始日と終了日の文字列を受け取り、日付オブジェクトのリストと総日数を返します。
    エラーが発生した場合はNoneを返します。
    """
    try:
        start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
    except ValueError:
        print(f"エラー: 日付形式が無効です。'{start_date_str}' または '{end_date_str}' をYYYY-MM-DD形式で入力してください。")
        return None
    
    if start_date > end_date:
        print(f"エラー: 開始日 '{start_date_str}' が終了日 '{end_date_str}' より後になっています。")
        return None

    date_list = [start_date + datetime.timedelta(days=i) for i in range((end_date - start_date).days + 1)]
    return date_list, len(date_list)

def build_shift_assignment_model(employee_ids: list, dates: list, shifts: list) -> tuple[cp_model.CpModel, dict]:
    """
    従業員IDリスト、日付リスト、シフトリストに基づき、OR-Toolsモデルと変数を構築します。
    基本制約（各従業員は各日に1シフト）もモデルに追加します。
    """
    model = cp_model.CpModel()
    num_employees = len(employee_ids)
    num_days = len(dates)
    num_shifts = len(shifts)

    x = {}  # 変数ディクショナリ: x[e_idx, d_idx, s_idx]
    for e_idx in range(num_employees):
        for d_idx in range(num_days):
            for s_idx in range(num_shifts):
                # 変数名に職員IDを含めるとデバッグ時に役立つことがあるが、長くなるのでインデックスのみも一案
                x[e_idx, d_idx, s_idx] = model.NewBoolVar(f'x_emp{employee_ids[e_idx]}_day{d_idx}_shift{shifts[s_idx]}')

    # 制約: 各従業員は、各日に、いずれか1つのシフトに必ず割り当てられる
    for e_idx in range(num_employees):
        for d_idx in range(num_days):
            model.Add(sum(x[e_idx, d_idx, s_idx] for s_idx in range(num_shifts)) == 1)
            
    return model, x

def add_staffing_constraints(
    model: cp_model.CpModel, 
    variables: dict, 
    employee_info_df: pd.DataFrame, 
    dates: list[datetime.date], 
    shifts: list[str], 
    staffing_rules: dict
) -> list:
    """
    施設の人員配置ルールをモデルに制約として追加します。
    ルールにはハード制約とソフト制約の概念を含みます。
    ソフト制約の場合、ペナルティ変数をリストで返します。
    """
    num_employees = len(employee_info_df)
    employee_ids = employee_info_df["職員ID"].tolist()
    penalty_terms = [] # ソフト制約のペナルティ項を格納するリスト

    for d_idx, date_obj in enumerate(dates):
        for floor, rules_for_floor in staffing_rules.items():
            # このフロアに所属する従業員のインデックスを取得
            floor_employee_indices = [
                e_idx for e_idx, emp_id in enumerate(employee_ids) 
                if employee_info_df.loc[employee_info_df["職員ID"] == emp_id, "担当フロア"].iloc[0] == floor
            ]
            if not floor_employee_indices:
                print(f"警告: フロア'{floor}'に所属する従業員が見つかりませんでした。このフロアの配置制約はスキップされます。")
                continue

            for shift_name, rule_details in rules_for_floor.items():
                target_staff_count = rule_details.get("target")
                constraint_type = rule_details.get("constraint_type", "hard") # デフォルトはhard
                
                s_idx = -1
                try:
                    s_idx = shifts.index(shift_name)
                except ValueError:
                    print(f"警告: ルール定義内のシフト名'{shift_name}'が基本シフトリストに存在しません。このルールはスキップされます。")
                    continue

                if target_staff_count is None:
                    print(f"警告: フロア'{floor}'のシフト'{shift_name}'の目標人数が未定義です。このルールはスキップされます。")
                    continue

                # このフロアの従業員が、この日に、このシフトに割り当てられる総数
                current_shift_vars = [variables[e_idx, d_idx, s_idx] for e_idx in floor_employee_indices]
                
                if constraint_type == "hard":
                    model.Add(sum(current_shift_vars) == target_staff_count)
                    # print(f"ハード制約追加: {date_obj.strftime('%Y-%m-%d')} フロア{floor} シフト{shift_name} = {target_staff_count}人")
                elif constraint_type == "soft":
                    under_penalty_weight = rule_details.get("under_penalty_weight", 0)
                    over_penalty_weight = rule_details.get("over_penalty_weight", 0)

                    # 目標人数との差分
                    actual_staff_sum = sum(current_shift_vars)
                    
                    # 不足人数変数 (0以上)
                    shortage = model.NewIntVar(0, target_staff_count, f'shortage_floor{floor}_day{d_idx}_shift{shift_name}')
                    # 過剰人数変数 (0以上)
                    excess = model.NewIntVar(0, len(floor_employee_indices) - target_staff_count, f'excess_floor{floor}_day{d_idx}_shift{shift_name}')
                    
                    # actual_staff_sum - target_staff_count = excess - shortage
                    # target_staff_count - actual_staff_sum = shortage - excess
                    model.Add(target_staff_count - actual_staff_sum == shortage - excess)

                    if under_penalty_weight > 0:
                        penalty_terms.append(shortage * under_penalty_weight)
                    if over_penalty_weight > 0:
                        penalty_terms.append(excess * over_penalty_weight)
                    
                    print(f"情報: ソフト制約を適用中: {date_obj.strftime('%Y-%m-%d')} フロア{floor} シフト{shift_name} 目標{target_staff_count}人 (不足ペナルティ重み:{under_penalty_weight}, 過剰ペナルティ重み:{over_penalty_weight})")

                else:
                    print(f"警告: 不明な制約タイプ'{constraint_type}'です。フロア'{floor}'のシフト'{shift_name}'のルールはスキップされます。")
    return penalty_terms

def add_min_holidays_constraint(
    model: cp_model.CpModel,
    variables: dict,
    employee_info_df: pd.DataFrame,
    dates: list[datetime.date],
    shifts: list[str],
    min_holidays: int,
    target_employment_type: str = "常勤" # 対象とする雇用形態
):
    """
    指定された雇用形態の従業員が、期間中に最低限取得すべき公休日数を確保する制約をモデルに追加します。
    """
    num_days = len(dates)
    try:
        holiday_shift_idx = shifts.index("公休")
    except ValueError:
        print("エラー: シフトリストに '公休' が見つかりません。公休確保制約は追加できません。")
        return

    for e_idx, emp_row in employee_info_df.iterrows():
        if emp_row["常勤/パート"] == target_employment_type:
            employee_id = emp_row["職員ID"]
            # この従業員の期間中の総公休日数を表す変数リスト
            employee_holidays_vars = [variables[e_idx, d_idx, holiday_shift_idx] for d_idx in range(num_days)]
            
            # 制約: 総公休日数 >= min_holidays
            model.Add(sum(employee_holidays_vars) >= min_holidays)
            print(f"制約追加: 職員ID {employee_id} ({target_employment_type}) の公休日数 >= {min_holidays}日")

def solve_and_get_results(model: cp_model.CpModel, employee_ids: list, dates: list, shifts: list, variables: dict) -> pd.DataFrame | None:
    """
    OR-Toolsモデルを解き、結果をpandas DataFrameとして整形して返します。
    DataFrameのindexは職員ID、列は日付文字列、値は割り当てられたシフト名。
    解が見つからない場合はNoneを返します。
    """
    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        print("解が見つかりました。シフト割り当て結果を生成中...")
        
        # 直接DataFrameを作成するより、辞書のリスト経由の方が柔軟な場合がある
        # ここでは index と columns を指定して DataFrame を初期化し、値を埋める
        date_str_columns = [d.strftime("%Y-%m-%d") for d in dates]
        results_df = pd.DataFrame(index=employee_ids, columns=date_str_columns)
        results_df.index.name = "職員ID" # index名を明示

        for e_idx, emp_id in enumerate(employee_ids):
            for d_idx, date_obj in enumerate(dates):
                date_str = date_obj.strftime("%Y-%m-%d")
                for s_idx, shift_name in enumerate(shifts):
                    if solver.Value(variables[e_idx, d_idx, s_idx]) == 1:
                        results_df.loc[emp_id, date_str] = shift_name
                        break # 1つのシフトが見つかればOK
        return results_df
    elif status == cp_model.INFEASIBLE:
        print("解が見つかりませんでした (INFEASIBLE)。制約が矛盾している可能性があります。")
        # 従業員数、必要人数などの詳細情報をログに出力するとデバッグに役立つ
        return None
    elif status == cp_model.MODEL_INVALID:
        print("モデルが無効です (MODEL_INVALID)。")
        return None
    else:
        print(f"ソルバーが予期しないステータスで終了しました: {status}")
        return None

# save_results_to_csv は output_utils.py に移動

def main():
    """
    シフト作成プロセスのメインコントローラー。
    """
    print("シフト作成処理を開始します...")

    # 1. データの読み込みと準備
    employee_info_df = load_employee_data(EMPLOYEE_FILEPATH)
    if employee_info_df is None:
        print("従業員データの読み込みに失敗したため、処理を中断します。")
        return
    employee_ids = employee_info_df["職員ID"].tolist() # モデル構築用

    date_info = generate_date_range(START_DATE_STR, END_DATE_STR)
    if date_info is None:
        print("日付範囲の生成に失敗したため、処理を中断します。")
        return
    dates, num_days = date_info 

    print(f"対象期間: {START_DATE_STR} から {END_DATE_STR} ({num_days}日間)")
    print(f"対象従業員数: {len(employee_ids)}人")
    print(f"シフト種類: {', '.join(SHIFTS)}")

    # 2. モデルの構築
    print("シフト割り当てモデルを構築中...")
    model, variables = build_shift_assignment_model(employee_ids, dates, SHIFTS)

    # --- 施設ルール定義 ---
    facility_staffing_rules = {
        "1F": {
            "早出": {"target": 2, "constraint_type": "hard"},
            "日勤": {"target": 4, "constraint_type": "hard"},
            "夜勤": {"target": 2, "constraint_type": "hard"},
            # "公休": {"target": 9, "constraint_type": "hard"} # 1Fの残り人数 (17 - (2+4+2) = 9)
            "明勤": { # ソフト制約のテストケース
                "target": 1, 
                "constraint_type": "soft",
                "under_penalty_weight": 10, # 不足の場合、重めのペナルティ
                "over_penalty_weight": 1    # 過剰の場合は軽めのペナルティ
            }
        }
        # 他のフロアのルールもここに追加可能
    }
    print(f"適用する施設人員配置ルール: {facility_staffing_rules}")
    # add_staffing_constraints はペナルティ項のリストを返すようになった
    all_penalty_terms = add_staffing_constraints(model, variables, employee_info_df, dates, SHIFTS, facility_staffing_rules)
    
    # 目的関数: ソフト制約のペナルティ総和を最小化
    if all_penalty_terms:
        model.Minimize(sum(all_penalty_terms))
    # --- ここまで施設ルール ---

    # --- 個人ルール定義 ---
    # 例: 常勤職員は期間中に8日以上の公休を取得
    MIN_HOLIDAYS_FOR_FULL_TIME = 8
    if "常勤/パート" in employee_info_df.columns: 
        add_min_holidays_constraint(
            model, 
            variables, 
            employee_info_df, 
            dates, 
            SHIFTS, 
            MIN_HOLIDAYS_FOR_FULL_TIME,
            target_employment_type="常勤" 
        )
    else:
        print("警告: 従業員情報に '常勤/パート' 列が見つからないため、公休確保制約はスキップされました。")
    # --- ここまで個人ルール ---

    # 3. モデルの解決と結果取得
    # solve_and_get_results に渡すのは employee_ids のリスト
    assigned_shifts_df = solve_and_get_results(model, employee_ids, dates, SHIFTS, variables)

    # 4. 結果の保存
    if assigned_shifts_df is not None:
        save_results_to_csv(
            assigned_shifts_df, 
            employee_info_df, # 職員名と担当フロアを含むDF
            dates, 
            HOLIDAYS_2025_APR_MAY, 
            SHIFTS, # 全シフト種類 (個人集計用)
            SHIFTS_FOR_AGGREGATION, # 個人集計の対象シフト名
            WORKING_SHIFTS_FOR_DAILY_TOTAL # 日付別合計の対象シフト名
        )
    else:
        print("シフト表の生成に失敗しました。CSVファイルは出力されません。")

    print("シフト作成処理を終了します。")


if __name__ == '__main__':
    main() 