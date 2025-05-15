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
    rule_details: dict # 個別のルール詳細 (min_days, constraint_type, under_penalty_weightなどを含む)
) -> list:
    """
    従業員の最低公休日数に関する制約（ハードまたはソフト）をモデルに追加します。
    ルール詳細は辞書で渡されます。
    """
    num_days = len(dates)
    penalty_terms = []

    min_holidays = rule_details.get("min_days")
    target_employment_type = rule_details.get("target_employment_type", "常勤") # デフォルト値も維持
    constraint_type = rule_details.get("constraint_type", "hard")
    under_penalty_weight = rule_details.get("under_penalty_weight", 0)

    if min_holidays is None:
        print(f"警告: 最低公休日数ルールの min_days が未定義です。ルールはスキップされます。詳細: {rule_details}")
        return penalty_terms

    try:
        holiday_shift_idx = shifts.index("公休")
    except ValueError:
        print("エラー: シフトリストに '公休' が見つかりません。公休確保制約は追加できません。")
        return penalty_terms

    for e_idx, emp_row in employee_info_df.iterrows():
        if emp_row["常勤/パート"] == target_employment_type:
            employee_id = emp_row["職員ID"]
            employee_holidays_vars = [variables[e_idx, d_idx, holiday_shift_idx] for d_idx in range(num_days)]
            actual_holidays_sum = sum(employee_holidays_vars)

            if constraint_type == "hard":
                model.Add(actual_holidays_sum >= min_holidays)
                print(f"ハード制約追加: 職員ID {employee_id} ({target_employment_type}) の公休日数 >= {min_holidays}日")
            elif constraint_type == "soft" and under_penalty_weight > 0:
                shortage = model.NewIntVar(0, min_holidays, f'shortage_holidays_emp{employee_id}')
                model.Add(actual_holidays_sum + shortage >= min_holidays)
                penalty_terms.append(shortage * under_penalty_weight)
                print(f"ソフト制約追加: 職員ID {employee_id} ({target_employment_type}) の公休日数目標 {min_holidays}日 (不足ペナルティ重み:{under_penalty_weight})")
    return penalty_terms

def add_max_consecutive_workdays_constraint(
    model: cp_model.CpModel,
    variables: dict,
    employee_ids: list, 
    dates: list[datetime.date],
    shifts: list[str],
    rule_details: dict 
) -> list:
    """
    従業員の最大連続勤務日数に関する制約（ハードまたはソフト）をモデルに追加します。
    """
    penalty_terms = []
    num_employees = len(employee_ids)
    num_days = len(dates)
    
    max_consecutive_days = rule_details.get("max_days")
    work_shift_names = rule_details.get("work_shifts", [])
    constraint_type = rule_details.get("constraint_type", "hard")
    over_penalty_weight = rule_details.get("over_penalty_weight", 0) # ソフト制約で超過した場合のペナルティ

    if not work_shift_names:
        print("警告: 連続勤務日数制約の work_shifts が空です。制約はスキップされます。")
        return penalty_terms
    if max_consecutive_days is None or max_consecutive_days <= 0:
        print(f"警告: 連続勤務日数制約の max_days ({max_consecutive_days}) が無効です。制約はスキップされます。")
        return penalty_terms

    work_shift_indices = [s_idx for s_idx, s_name in enumerate(shifts) if s_name in work_shift_names]
    if not work_shift_indices:
        print(f"警告: 連続勤務日数制約の work_shifts {work_shift_names} が基本シフトリストに存在しません。制約はスキップされます。")
        return penalty_terms
    
    window_size = max_consecutive_days + 1

    for e_idx in range(num_employees):
        emp_id = employee_ids[e_idx] # デバッグや変数名用に取得
        for d_idx in range(num_days - window_size + 1):
            vars_in_window = []
            for day_offset in range(window_size):
                for s_idx in work_shift_indices:
                    vars_in_window.append(variables[e_idx, d_idx + day_offset, s_idx])
            
            if constraint_type == "hard":
                # ウィンドウ内の総勤務日数が max_consecutive_days を超えてはならない
                model.Add(sum(vars_in_window) <= max_consecutive_days)
            elif constraint_type == "soft" and over_penalty_weight > 0:
                # 超過日数を表す変数 (0以上、ウィンドウ内の最大可能超過日数まで)
                # 例: max_days=4, window_size=5 の場合、最大超過は1 (5日全て勤務した場合の超過分)
                # この変数は、(実際の勤務日数 - max_consecutive_days) の正の部分を捉える
                max_possible_excess_in_window = window_size - max_consecutive_days
                # ただし、実際の勤務が max_consecutive_days より少ない場合は超過は0。よって上限はもっとタイトにできる。
                # excess_days の上限は、ウィンドウ内で勤務とみなされるシフトに割り当てられる最大日数からmax_consecutive_daysを引いた値だが、
                # 簡単のため、ここでは window_size - max_consecutive_days で十分 (IntVarの上限はソルバー性能に影響小)
                excess_days = model.NewIntVar(0, max_possible_excess_in_window, f'excess_consecutive_work_emp{emp_id}_day{d_idx}')
                
                # 制約: 実際の勤務日数 - max_consecutive_days <= 超過日数
                # これにより、超過日数が0より大きい場合、excess_days がその超過分以上になるようにする
                model.Add(sum(vars_in_window) - max_consecutive_days <= excess_days)
                penalty_terms.append(excess_days * over_penalty_weight)

    if constraint_type == "hard":
         print(f"ハード制約追加: 全従業員の連続勤務日数を最大 {max_consecutive_days} 日までに制限 (勤務対象: {work_shift_names})")
    elif constraint_type == "soft" and over_penalty_weight > 0:
         print(f"ソフト制約追加: 全従業員の連続勤務日数目標 最大 {max_consecutive_days} 日まで (超過ペナルティ重み:{over_penalty_weight}, 勤務対象: {work_shift_names})")
            
    return penalty_terms

def add_sequential_shift_constraint(
    model: cp_model.CpModel,
    variables: dict,
    employee_ids: list,
    dates: list[datetime.date],
    shifts: list[str],
    rule_details: dict # previous_shift_name, next_shift_name, constraint_type, penalty_weight
) -> list:
    """
    指定された「前のシフト」の翌日に、指定された「次のシフト」が来るように制約を追加します。
    ハード制約またはソフト制約として機能します。
    ソフト制約の場合、ペナルティ項のリストを返します。
    """
    num_employees = len(employee_ids)
    num_days = len(dates)
    penalty_terms = []

    previous_shift_name = rule_details.get("previous_shift_name")
    next_shift_name = rule_details.get("next_shift_name")
    constraint_type = rule_details.get("constraint_type", "hard") # デフォルトはハード
    penalty_weight = rule_details.get("penalty_weight", 0) # ソフト制約時のペナルティ

    if not previous_shift_name or not next_shift_name:
        print("エラー: シーケンス制約の previous_shift_name または next_shift_name が未定義です。制約はスキップされます。")
        return penalty_terms

    try:
        prev_s_idx = shifts.index(previous_shift_name)
    except ValueError:
        print(f"エラー: シフトリストに指定された前のシフト '{previous_shift_name}' が見つかりません。シーケンス制約は追加できません。")
        return penalty_terms
    
    try:
        next_s_idx = shifts.index(next_shift_name)
    except ValueError:
        print(f"エラー: シフトリストに指定された次のシフト '{next_shift_name}' が見つかりません。シーケンス制約は追加できません。")
        return penalty_terms

    for e_idx, emp_id in enumerate(employee_ids): # emp_id を変数名に使用するために enumerate を使う
        for d_idx in range(num_days - 1): # 最終日は翌日がないためループしない
            
            prev_shift_assigned_var = variables[e_idx, d_idx, prev_s_idx]
            next_shift_assigned_var = variables[e_idx, d_idx + 1, next_s_idx]

            if constraint_type == "hard":
                model.AddImplication(prev_shift_assigned_var, next_shift_assigned_var)
            elif constraint_type == "soft" and penalty_weight > 0:
                # 違反条件: prev_shift_assigned_var が True かつ next_shift_assigned_var が False
                # penalty_violation が True のときペナルティ
                penalty_violation = model.NewBoolVar(f'seq_violation_emp{emp_id}_day{d_idx}_{previous_shift_name}_to_{next_shift_name}')
                
                # (NOT prev_assigned) OR (next_assigned) OR (penalty_violation)
                # これにより、prev_assigned=True かつ next_assigned=False の場合に penalty_violation=True が強制される。
                # それ以外の場合は penalty_violation は 0 になることが期待される（目的関数で最小化されるため）。
                model.AddBoolOr([
                    prev_shift_assigned_var.Not(), 
                    next_shift_assigned_var, 
                    penalty_violation
                ])
                penalty_terms.append(penalty_violation * penalty_weight)
            # constraint_type が "soft" で penalty_weight が 0 の場合は何もしない (実質ハード制約だがメッセージはソフトになる)

    if constraint_type == "hard":
        print(f"ハード制約追加: 全従業員に対し、'{previous_shift_name}' の翌日は必ず '{next_shift_name}' にする。")
    elif constraint_type == "soft" and penalty_weight > 0:
        print(f"ソフト制約追加: 全従業員に対し、'{previous_shift_name}' の翌日を '{next_shift_name}' にする目標 (違反ペナルティ重み:{penalty_weight})。")
            
    return penalty_terms

def add_assignment_balance_constraint(
    model: cp_model.CpModel,
    variables: dict,
    employee_info_df: pd.DataFrame,
    dates: list[datetime.date],
    shifts: list[str],
    rule_details: dict # target_employment_type, target_shift_name, constraint_type, penalty_weight, max_diff_allowed
) -> list:
    """
    指定された従業員グループ内での特定シフトの割り当て回数を平準化する制約を追加します。
    ハード制約（最大差の制限）またはソフト制約（最小最大差へのペナルティ）として機能します。
    """
    penalty_terms = []
    num_days = len(dates)

    target_employment_type = rule_details.get("target_employment_type")
    target_shift_name = rule_details.get("target_shift_name")
    constraint_type = rule_details.get("constraint_type", "soft") # デフォルトはソフト制約
    penalty_weight = rule_details.get("penalty_weight", 0)
    max_diff_allowed = rule_details.get("max_diff_allowed") # ハード制約時に使用

    if not target_employment_type or not target_shift_name:
        print("エラー: 割り当て平準化制約の target_employment_type または target_shift_name が未定義です。制約はスキップされます。")
        return penalty_terms
    
    if constraint_type == "soft" and penalty_weight <= 0:
        print(f"情報: 割り当て平準化ソフト制約 ({target_employment_type}, {target_shift_name}) の penalty_weight が0以下です。実質的に効果はありません。")
        return penalty_terms
    if constraint_type == "hard" and (max_diff_allowed is None or max_diff_allowed < 0):
        print(f"エラー: 割り当て平準化ハード制約 ({target_employment_type}, {target_shift_name}) の max_diff_allowed が未定義または負数です。制約はスキップされます。")
        return penalty_terms

    try:
        target_s_idx = shifts.index(target_shift_name)
    except ValueError:
        print(f"エラー: シフトリストに指定された対象シフト '{target_shift_name}' が見つかりません。割り当て平準化制約は追加できません。")
        return penalty_terms

    # 対象となる従業員のインデックスリストを取得
    target_employee_indices = employee_info_df[
        employee_info_df["常勤/パート"] == target_employment_type
    ].index.tolist()

    if len(target_employee_indices) <= 1:
        print(f"情報: 割り当て平準化制約の対象となる '{target_employment_type}' の従業員が1名以下です。平準化制約はスキップされます。")
        return penalty_terms
    
    employee_ids = employee_info_df["職員ID"].tolist() # For variable naming

    # 各対象従業員の対象シフト割り当て回数を保持するIntVarのリスト
    num_assignments_vars = []
    for e_idx in target_employee_indices:
        emp_id = employee_ids[e_idx]
        current_employee_assignments = [
            variables[e_idx, d_idx, target_s_idx] for d_idx in range(num_days)
        ]
        num_assignments_for_emp = model.NewIntVar(0, num_days, f'num_{target_shift_name}_emp{emp_id}')
        model.Add(num_assignments_for_emp == sum(current_employee_assignments))
        num_assignments_vars.append(num_assignments_for_emp)
    
    # 割り当て回数の最小値と最大値
    min_assignments = model.NewIntVar(0, num_days, f'min_assigned_{target_shift_name}_{target_employment_type}')
    max_assignments = model.NewIntVar(0, num_days, f'max_assigned_{target_shift_name}_{target_employment_type}')
    
    model.AddMinEquality(min_assignments, num_assignments_vars)
    model.AddMaxEquality(max_assignments, num_assignments_vars)
    
    # 最小値と最大値の差
    diff_assignments = model.NewIntVar(0, num_days, f'diff_assigned_{target_shift_name}_{target_employment_type}')
    model.Add(diff_assignments == max_assignments - min_assignments)
    
    if constraint_type == "hard":
        model.Add(diff_assignments <= max_diff_allowed)
        print(f"ハード制約追加: '{target_employment_type}' の '{target_shift_name}' 割り当て回数の差を最大 {max_diff_allowed} までに制限。")
    elif constraint_type == "soft": # penalty_weight > 0 は既にチェック済み
        penalty_terms.append(diff_assignments * penalty_weight)
        print(f"ソフト制約追加: '{target_employment_type}' の '{target_shift_name}' 割り当て回数を平準化 (最小最大差ペナルティ重み:{penalty_weight})。")
    
    return penalty_terms

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
    
    # --- ここまで施設ルール ---

    # --- 個人ルール定義 ---
    # 例: 常勤職員は期間中に8日以上の公休を取得
    MIN_HOLIDAYS_FOR_FULL_TIME = 8
    # 最低公休日の制約タイプとペナルティウェイト
    MIN_HOLIDAYS_CONSTRAINT_TYPE = "soft" # "hard" または "soft"
    MIN_HOLIDAYS_UNDER_PENALTY_WEIGHT = 10  # 不足時のペナルティ

    if "常勤/パート" in employee_info_df.columns: 
        personal_penalty_terms = add_min_holidays_constraint(
            model, 
            variables, 
            employee_info_df, 
            dates, 
            SHIFTS, 
            {
                "min_days": MIN_HOLIDAYS_FOR_FULL_TIME,
                "constraint_type": MIN_HOLIDAYS_CONSTRAINT_TYPE,
                "under_penalty_weight": MIN_HOLIDAYS_UNDER_PENALTY_WEIGHT,
                "target_employment_type": "常勤"
            }
        )
        all_penalty_terms.extend(personal_penalty_terms) # 施設ルールのペナルティに追加
    else:
        print("警告: 従業員情報に '常勤/パート' 列が見つからないため、公休確保制約はスキップされました。")
    
    # --- 連続勤務日数上限ルール ---
    max_consecutive_work_rule = {
        "max_days": 4,
        "work_shifts": ["日勤", "早出", "夜勤", "明勤"], # 明勤も勤務日としてカウント
        "constraint_type": "soft", # ハード制約からソフト制約に変更
        "over_penalty_weight": 10 # 超過した場合のペナルティウェイトを設定
    }
    consecutive_work_penalty_terms = add_max_consecutive_workdays_constraint(
        model,
        variables,
        employee_ids, # 従業員IDのリストを渡す
        dates,
        SHIFTS,
        max_consecutive_work_rule
    )
    all_penalty_terms.extend(consecutive_work_penalty_terms) # ソフト制約の場合に備えて追加
    # --- ここまで個人ルール (連続勤務日数) ---

    # --- シフトシーケンスルール ---
    # 例: 夜勤の翌日は明勤 (ソフト制約)
    night_to_ake_rule = {
        "previous_shift_name": "夜勤",
        "next_shift_name": "明勤",
        "constraint_type": "soft", # "hard" または "soft"
        "penalty_weight": 20 # 違反した場合のペナルティ (高めに設定する例)
    }
    sequence_penalty_terms = add_sequential_shift_constraint(
        model,
        variables,
        employee_ids,
        dates,
        SHIFTS,
        night_to_ake_rule
    )
    all_penalty_terms.extend(sequence_penalty_terms)

    # --- 割り当て回数平準化ルール ---
    # 常勤職員の公休数を平準化
    balance_holidays_rule = {
        "target_employment_type": "常勤",
        "target_shift_name": "公休",
        "penalty_weight": 1, # ペナルティは軽めに設定する例
        "max_diff_allowed": 1 # ハード制約時に使用
    }
    balance_penalty_terms_holidays = add_assignment_balance_constraint(
        model, variables, employee_info_df, dates, SHIFTS, balance_holidays_rule
    )
    all_penalty_terms.extend(balance_penalty_terms_holidays)

    # 常勤職員の夜勤数を平準化
    balance_night_shifts_rule = {
        "target_employment_type": "常勤",
        "target_shift_name": "夜勤",
        "penalty_weight": 2, # 公休よりは少し重めに設定する例
        "max_diff_allowed": 1 # ハード制約時に使用
    }
    balance_penalty_terms_night = add_assignment_balance_constraint(
        model, variables, employee_info_df, dates, SHIFTS, balance_night_shifts_rule
    )
    all_penalty_terms.extend(balance_penalty_terms_night)
    # --- ここまで割り当て回数平準化ルール ---

    # 3. モデルの解決と結果取得
    # 目的関数: ソフト制約のペナルティ総和を最小化
    if all_penalty_terms:
        model.Minimize(sum(all_penalty_terms))
    else:
        # ペナルティ項がない場合（すべてハード制約のみ、またはソフト制約がペナルティ0の場合）
        # 何かしらの目的関数がないと Solve() がエラーになることがあるため、ダミーの目的関数を設定するか、
        # このケースでは実行可能な解を見つけること自体が目的なので、Minimize(0) などでも良い。
        # もしくは、この段階でソフト制約がないことがわかっていれば Minimize を呼ばなくても良いかもしれないが、
        # OR-Tools の挙動として目的関数なしで Solve できるかは要確認。
        # 安全のため、ペナルティがなければ特に Minimize しないこととする (実行可能解探索)
        pass

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