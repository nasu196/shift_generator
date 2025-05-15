# 制約条件管理

## 基本設計思想

各制約条件について、以下の2種類の制約タイプを選択可能とすることを目標とします。

-   **ハード制約 (Hard Constraint):** 必ず満たされなければならない制約。この制約を破る解は許容されません。
-   **ソフト制約 (Soft Constraint):** 満たすことが望ましいが、必ずしも必須ではない制約。この制約を破った場合には、その度合いに応じてペナルティが課され、最適化の過程でペナルティの総和が最小になるように調整されます。

ルール定義の明確化と関数のインターフェース統一のため、各制約ルールに関するパラメータは、可能な限り**辞書型オブジェクトにまとめて**担当関数に渡すことを推奨します。

## 実装済み制約一覧

以下に、現在までにハード制約・ソフト制約の選択機能が実装された制約条件をリストアップします。

### 1. 施設の人員配置ルール

-   **担当関数:** `add_staffing_constraints` (於 `src/shift_model.py`)
-   **概要:** フロアごと、およびシフト種類ごとに必要な人員数を定義します。
-   **設定方法:** `facility_staffing_rules` ディクショナリ内で、各シフトルールに必要なパラメータ（`target`, `constraint_type`, `under_penalty_weight`, `over_penalty_weight` 等）をキーと値のペアで指定します。
    ```python
    # main関数内での設定例
    facility_staffing_rules = {
        "1F": {
            "早出": {"target": 2, "constraint_type": "hard"}, # ハード制約の例
            "明勤": { # ソフト制約の例
                "target": 1,
                "constraint_type": "soft",
                "under_penalty_weight": 10, # 目標人数に不足した場合のペナルティ
                "over_penalty_weight": 1    # 目標人数を超過した場合のペナルティ
            }
        }
        # 他のフロアやシフトのルールも同様に追加
    }

    # ... (中略) ...

    all_penalty_terms = add_staffing_constraints(
        model, variables, employee_info_df, dates, SHIFTS, facility_staffing_rules
    )
    ```
-   **ハード制約時:** 指定された `target` 人数と完全に一致するよう強制されます。
-   **ソフト制約時:**
    -   `target` 人数に対して不足が発生した場合、`shortage` 変数（不足人数）に `under_penalty_weight` を乗じた値がペナルティとして加算されます。
    -   `target` 人数に対して過剰が発生した場合、`excess` 変数（過剰人数）に `over_penalty_weight` を乗じた値がペナルティとして加算されます。
-   **実装状況:** 完了

### 2. 個人の最低公休日数ルール

-   **担当関数:** `add_min_holidays_constraint` (於 `src/shift_model.py`)
-   **概要:** 指定された雇用形態の従業員が、指定された期間中に取得すべき最低限の公休日数を定義します。
-   **設定方法:** `main` 関数内でルール詳細を辞書として定義し、`add_min_holidays_constraint` 関数に渡します。
    ```python
    # main関数内での設定例
    MIN_HOLIDAYS_FOR_FULL_TIME = 8
    MIN_HOLIDAYS_CONSTRAINT_TYPE = "soft"  # "hard" または "soft"
    MIN_HOLIDAYS_UNDER_PENALTY_WEIGHT = 10  # 不足時のペナルティ
    MIN_HOLIDAYS_TARGET_EMPLOYMENT_TYPE = "常勤"

    min_holidays_rule_details = {
        "min_days": MIN_HOLIDAYS_FOR_FULL_TIME,
        "target_employment_type": MIN_HOLIDAYS_TARGET_EMPLOYMENT_TYPE,
        "constraint_type": MIN_HOLIDAYS_CONSTRAINT_TYPE,
        "under_penalty_weight": MIN_HOLIDAYS_UNDER_PENALTY_WEIGHT
    }

    # ... (中略) ...

    if "常勤/パート" in employee_info_df.columns: # 対象列の存在確認
        personal_penalty_terms = add_min_holidays_constraint(
            model,
            variables,
            employee_info_df,
            dates,
            SHIFTS,
            min_holidays_rule_details # ルール詳細を辞書で渡す
        )
        all_penalty_terms.extend(personal_penalty_terms)
    ```
-   **ハード制約時 (`constraint_type="hard"`)**:
    -   従業員の総公休日数が、指定された `min_days` 以上であることが強制されます。
-   **ソフト制約時 (`constraint_type="soft"`)**:
    -   従業員の総公休日数が `min_days` に満たない場合、その不足日数 (`shortage`) に `under_penalty_weight` を乗じた値がペナルティとして加算されます。
-   **実装状況:** 完了

### 3. 個人の最大連続勤務日数ルール

-   **担当関数:** `add_max_consecutive_workdays_constraint` (於 `src/shift_model.py`)
-   **概要:** 全従業員に対し、指定された日数を超える連続勤務（指定された勤務シフトが連続すること）を制限します。
-   **設定方法:** `main` 関数内でルール詳細を辞書として定義し、`add_max_consecutive_workdays_constraint` 関数に渡します。
    ```python
    # main関数内での設定例
    max_consecutive_work_rule = {
        "max_days": 4, # 最大連続勤務日数
        "work_shifts": ["日勤", "早出", "夜勤", "明勤"], # 勤務とみなすシフト
        "constraint_type": "soft", # "hard" または "soft"
        "over_penalty_weight": 10  # 超過した場合のペナルティ (ソフト制約時のみ有効)
    }

    # ... (中略) ...

    consecutive_work_penalty_terms = add_max_consecutive_workdays_constraint(
        model,
        variables,
        employee_ids,
        dates,
        SHIFTS,
        max_consecutive_work_rule # ルール詳細を辞書で渡す
    )
    all_penalty_terms.extend(consecutive_work_penalty_terms)
    ```
-   **ハード制約時 (`constraint_type="hard"`)**:
    -   指定された `work_shifts` が `max_days` を超えて連続しないように強制されます。
-   **ソフト制約時 (`constraint_type="soft"`)**:
    -   `max_days` を超えて連続勤務が発生した場合、その超過した日数に対して `over_penalty_weight` を乗じた値がペナルティとして加算されます。
-   **実装状況:** 完了

### 4. 特定のシフトシーケンスルール

-   **担当関数:** `add_sequential_shift_constraint` (於 `src/shift_model.py`)
-   **概要:** ある指定したシフト (`previous_shift_name`) が割り当てられた場合、その翌日には指定した別のシフト (`next_shift_name`) が割り当てられることを目指します。ハード制約またはソフト制約として設定可能です。
-   **設定方法:** `main` 関数内でルール詳細を辞書 (`rule_details`) として定義し、`add_sequential_shift_constraint` 関数に渡します。辞書には以下のキーを含めます:
    -   `previous_shift_name` (str): 前日のシフト名。
    -   `next_shift_name` (str): 翌日に期待されるシフト名。
    -   `constraint_type` (str): "hard" または "soft"。
    -   `penalty_weight` (int, optional): ソフト制約の場合のペナルティの重み。`constraint_type`が`soft`でこの値が0より大きい場合に有効。

    ```python
    # main関数内での設定例 (夜勤の翌日は明勤 - ソフト制約)
    night_to_ake_rule = {
        "previous_shift_name": "夜勤",
        "next_shift_name": "明勤",
        "constraint_type": "soft",
        "penalty_weight": 20 
    }
    sequence_penalty_terms = add_sequential_shift_constraint(
        model, variables, employee_ids, dates, SHIFTS, night_to_ake_rule
    )
    all_penalty_terms.extend(sequence_penalty_terms)

    # main関数内での設定例 (明勤の翌日は公休 - ハード制約)
    ake_to_kokyu_rule = {
        "previous_shift_name": "明勤",
        "next_shift_name": "公休",
        "constraint_type": "hard"
    }
    # ハード制約の場合、返り値のリストは空なので all_penalty_terms への追加は任意
    add_sequential_shift_constraint(
        model, variables, employee_ids, dates, SHIFTS, ake_to_kokyu_rule
    ) 
    ```
-   **ハード制約時 (`constraint_type="hard"`)**:
    -   指定された `previous_shift_name` がある従業員のある日に割り当てられた場合、その従業員の翌日には必ず `next_shift_name` が割り当てられます。
-   **ソフト制約時 (`constraint_type="soft"`)**:
    -   `previous_shift_name` の翌日が `next_shift_name` でなかった場合、その違反に対して `penalty_weight` で指定されたペナルティが課されます。
-   **共通の注意点:**
    -   このルールは期間の最終日には適用されません（翌日が存在しないため）。
    -   指定されたシフト名が `SHIFTS` 定数に存在しない場合、エラーメッセージが表示され制約は追加されません。
-   **実装状況:** 完了

### 5. 特定シフトの割り当て回数平準化ルール

-   **担当関数:** `add_assignment_balance_constraint` (於 `src/shift_model.py`)
-   **概要:** 指定された従業員グループ（例: 常勤職員）内において、特定のシフト（例: 公休、夜勤）が各従業員に割り当てられる回数をできるだけ均等にすることを目指す制約です。ハード制約（グループ内の割り当て回数の最大差を制限）またはソフト制約（グループ内の割り当て回数の最大差にペナルティ）として設定可能です。
-   **設定方法:** `main` 関数内でルール詳細を辞書 (`rule_details`) として定義し、`add_assignment_balance_constraint` 関数に渡します。辞書には以下のキーを含めます:
    -   `target_employment_type` (str): 平準化の対象とする従業員の雇用形態 (例: "常勤")。
    -   `target_shift_name` (str): 平準化の対象とするシフト名 (例: "公休", "夜勤")。
    -   `constraint_type` (str, optional): "hard" または "soft"。デフォルトは "soft"。
    -   `penalty_weight` (int, optional): ソフト制約の場合のペナルティの重み。`constraint_type`が`soft`でこの値が0より大きい場合に有効。
    -   `max_diff_allowed` (int, optional): ハード制約の場合に許容される、グループ内の割り当て回数の最大差。`constraint_type`が`hard`の場合に必要で、0以上の値を設定します。

    ```python
    # main関数内での設定例 (常勤職員の公休数を平準化 - ソフト制約)
    balance_holidays_rule_soft = {
        "target_employment_type": "常勤",
        "target_shift_name": "公休",
        "constraint_type": "soft",
        "penalty_weight": 1
    }
    # ... add_assignment_balance_constraint(..., balance_holidays_rule_soft)

    # main関数内での設定例 (常勤職員の夜勤数を平準化 - ハード制約)
    balance_night_shifts_rule_hard = {
        "target_employment_type": "常勤",
        "target_shift_name": "夜勤",
        "constraint_type": "hard",
        "max_diff_allowed": 1 # 常勤職員間の夜勤数の差は最大1回まで
    }
    # ... add_assignment_balance_constraint(..., balance_night_shifts_rule_hard)
    ```
-   **ハード制約時 (`constraint_type="hard"`)**:
    -   指定された `target_employment_type` の従業員グループ内での `target_shift_name` の総割り当て回数について、その最大値と最小値の差が `max_diff_allowed` 以下であることが強制されます。
-   **ソフト制約時 (`constraint_type="soft"`)**:
    -   指定された `target_employment_type` の従業員グループ内での `target_shift_name` の総割り当て回数について、その最大値と最小値の差に `penalty_weight` を乗じたものがペナルティとして目的関数に追加されます。
-   **共通の注意点:**
    -   対象となる従業員が1名以下の場合、この制約は実質的に適用されません。
    -   ハード制約時に `max_diff_allowed` が不適切（未指定または負数）な場合、またはソフト制約時に `penalty_weight` が0以下の場合は、制約は実質的に適用されないか、エラーメッセージが表示されることがあります。
    -   指定されたシフト名や雇用形態が存在しない場合は、エラーメッセージが表示され制約は追加されません。
-   **実装状況:** 完了

### 6. 個別シフト希望ルール

-   **担当関数:** `add_shift_request_constraint` (於 `src/shift_model.py`)
-   **概要:** 個々の従業員が特定の日付に特定のシフトを希望することを制約として扱います。ハード制約（指定シフトに完全固定）またはソフト制約（希望が叶わなかった場合にペナルティ）として設定可能です。
-   **設定方法:** `main` 関数内で、シフト希望のリスト (`shift_requests`) を定義します。各希望は以下のキーを持つ辞書です:
    -   `employee_id` (str): 希望を出す従業員のID。
    -   `date_str` (str): 希望する日付（"YYYY-MM-DD"形式）。
    -   `requested_shift` (str): 希望するシフト名（例: "公休"）。
    -   `constraint_type` (str, optional): "hard" または "soft"。デフォルトは "soft"。
    -   `penalty_weight` (int, optional): ソフト制約の場合のペナルティの重み。`constraint_type`が`soft`でこの値が0より大きい場合に有効。
    このリストを `add_shift_request_constraint` 関数に渡します。

    ```python
    # main関数内での設定例
    individual_shift_requests = [
        # ソフト制約の例
        {"employee_id": "A001", "date_str": "2025-04-15", "requested_shift": "公休", "constraint_type": "soft", "penalty_weight": 30},
        # ハード制約の例 (この従業員のこの日は必ず公休になる)
        {"employee_id": "B002", "date_str": "2025-04-20", "requested_shift": "公休", "constraint_type": "hard"},
        # 公休以外の希望も可能 (ソフト制約)
        {"employee_id": "C003", "date_str": "2025-05-01", "requested_shift": "夜勤", "constraint_type": "soft", "penalty_weight": 10}
    ]
    # ... add_shift_request_constraint(..., individual_shift_requests)
    ```
-   **ハード制約時 (`constraint_type="hard"`)**:
    -   指定された従業員の指定された日付のシフトは、`requested_shift` に完全に固定されます。
-   **ソフト制約時 (`constraint_type="soft"`)**:
    -   指定された従業員が指定された日に `requested_shift` に割り当てられなかった場合に、`penalty_weight` で指定されたペナルティが課されます。
-   **共通の注意点:**
    -   従業員ID、日付、シフト名が無効な場合や、日付が対象期間外の場合は、該当する希望ルールはスキップされ、警告メッセージが表示されることがあります。
    -   ソフト制約時に `penalty_weight` が0以下の場合は、実質的に効果はありません。
    -   **ハード制約で多くのシフトを固定しすぎると、他の制約との間で矛盾が生じ、実行可能な解が見つからなくなる (INFEASIBLE) リスクが高まります。使用には注意が必要です。**
-   **実装状況:** 完了

### 7. 特定ペアの同日同シフト禁止ルール (ハード制約)

-   **担当関数:** `add_avoid_same_shift_constraint` (於 `src/shift_model.py`)
-   **概要:** 指定された2名の従業員が、同じ日に、指定された禁止対象シフトのいずれかに同時に割り当てられることを禁止するハード制約です。
-   **設定方法:** `main` 関数内で、禁止ルールのリスト (`avoid_rules`) を定義します。各ルールは以下のキーを持つ辞書です:
    -   `employee_pair` (list[str]): 対象となる2名の従業員IDのリスト (例: `["A001", "B002"]`)。
    -   `avoid_shifts` (list[str]): 禁止対象となるシフト名のリスト (例: `["日勤", "夜勤"]`)。
    -   `constraint_type` (str): 現在は "hard" のみサポート。 (将来的に "soft" も検討可能)
    このリストを `add_avoid_same_shift_constraint` 関数に渡します。

    ```python
    # main関数内での設定例
    avoid_same_shift_rules = [
        {
            "employee_pair": ["A001", "B002"], 
            "avoid_shifts": ["日勤", "夜勤", "早出", "明勤"], # 禁止対象シフトの例
            "constraint_type": "hard"
        },
        {
            "employee_pair": ["C003", "D004"], 
            "avoid_shifts": ["早出"], # 単一シフトもリストで指定
            "constraint_type": "hard"
        }
    ]
    if employee_info_df is not None: # Noneチェックを追加
        # add_avoid_same_shift_constraint はペナルティ項を返さない（ハード制約のみのため）
        add_avoid_same_shift_constraint(
            model,
            variables,
            employee_info_df,
            dates,
            SHIFTS, # グローバル定数 SHIFTS を渡す
            avoid_same_shift_rules
        )
    ```
-   **ハード制約時 (`constraint_type="hard"`)**:
    -   指定された `employee_pair` の2名が、ある同じ日に、`avoid_shifts` リスト内のいずれかのシフトに同時に割り当てられることを禁止します。
-   **共通の注意点:**
    -   `employee_pair` に指定する従業員IDは、`employee_info_df` に存在する有効なIDである必要があります。
    -   `avoid_shifts` に指定するシフト名は、`SHIFTS` 定数に存在する有効なシフト名である必要があります。
    -   ルール定義が無効な場合（例: 従業員IDやシフト名が存在しない、ペアの人数が2名でないなど）、警告メッセージが表示され、該当ルールはスキップされることがあります。
    -   現在はハード制約のみサポートしています。
-   **実装状況:** 完了

### 8. 期間中総勤務日数制御ルール

-   **担当関数:** `add_total_workdays_constraint` (於 `src/shift_model.py`)
-   **概要:** 個々の従業員について、シフト対象期間中における総勤務日数を制御します。ハード制約（正確な日数、上限日数、下限日数のいずれかを指定）またはソフト制約（目標日数からの乖離、上限超過、下限不足に対してペナルティ）として設定可能です。
-   **設定方法:** `main` 関数内で、総勤務日数制御ルールのリスト (`total_workdays_rules`) を定義します。各ルールは以下のキーを持つ辞書です:
    -   `employee_id` (str): 対象となる従業員のID。
    -   `constraint_type` (str): 制約の種類。以下のいずれかを指定します:
        -   `"exact"`: 総勤務日数を指定された `days` に完全に一致させます（ハード制約）。
        -   `"max"`: 総勤務日数を指定された `days` 以下に制限します（ハード制約）。
        -   `"min"`: 総勤務日数を指定された `days` 以上に制限します（ハード制約）。
        -   `"soft_exact"`: 総勤務日数を指定された `days` に近づけます。差の絶対値に対してペナルティが課されます（ソフト制約）。
        -   `"soft_max"`: 総勤務日数が指定された `days` を超えた場合に、超過分に対してペナルティが課されます（ソフト制約）。
        -   `"soft_min"`: 総勤務日数が指定された `days` に満たない場合に、不足分に対してペナルティが課されます（ソフト制約）。
    -   `days` (int): 目標とする総勤務日数、または上限/下限となる総勤務日数。
    -   `penalty_weight` (int, optional): ソフト制約の場合のペナルティの重み。`constraint_type` がソフト制約（`soft_exact`, `soft_max`, `soft_min`）の場合に有効です。デフォルトは0。
-   **勤務日数のカウント対象:** `WORKING_SHIFTS_FOR_DAILY_TOTAL` 定数で定義されたシフト（例: "日勤", "早出", "夜勤", "明勤"）が勤務としてカウントされます。「公休」などは含まれません。

    ```python
    # main関数内での設定例
    total_workdays_rules = [
        # ハード制約の例
        {"employee_id": "A001", "constraint_type": "exact", "days": 20}, # A001は期間中ちょうど20日勤務
        {"employee_id": "B002", "constraint_type": "max", "days": 22},   # B002は期間中最大22日勤務
        {"employee_id": "C003", "constraint_type": "min", "days": 18},   # C003は期間中最低18日勤務
        
        # ソフト制約の例
        # D004は期間中20日勤務が目標。1日ずれるごとにペナルティ5
        {"employee_id": "D004", "constraint_type": "soft_exact", "days": 20, "penalty_weight": 5},
        # E005は期間中最大21日勤務が目標。21日を超えると1日超過あたりペナルティ10
        {"employee_id": "E005", "constraint_type": "soft_max", "days": 21, "penalty_weight": 10},
        # F006は期間中最低19日勤務が目標。19日に満たないと1日不足あたりペナルティ8
        {"employee_id": "F006", "constraint_type": "soft_min", "days": 19, "penalty_weight": 8},
        
        # 同じ従業員に複数の総勤務日数ルールを適用することも理論上は可能ですが、
        # ルール同士が矛盾しないように注意が必要です。
        # 例えば、A001に "exact": 20 と "soft_max": 19, penalty:10 を設定すると、
        # exact=20が優先され、soft_maxルールは常にペナルティ10を発生させることになります。
    ]
    # ...
    # if employee_info_df is not None:
    #     total_workdays_penalty_terms = add_total_workdays_constraint(
    #         model,
    #         variables,
    #         employee_info_df,
    #         dates,
    #         SHIFTS,
    #         total_workdays_rules
    #     )
    #     all_penalty_terms.extend(total_workdays_penalty_terms)
    ```
-   **ハード制約時 (`constraint_type` が `"exact"`, `"max"`, `"min"`)**:
    -   `"exact"`: 従業員の総勤務日数が、指定された `days` と完全に一致するように強制されます。
    -   `"max"`: 従業員の総勤務日数が、指定された `days` 以下になるように強制されます。
    -   `"min"`: 従業員の総勤務日数が、指定された `days` 以上になるように強制されます。
-   **ソフト制約時 (`constraint_type` が `"soft_exact"`, `"soft_max"`, `"soft_min"`)**:
    -   `"soft_exact"`: 従業員の総勤務日数が `days` から乖離した場合、その差の絶対値に `penalty_weight` を乗じた値がペナルティとして加算されます。
    -   `"soft_max"`: 従業員の総勤務日数が `days` を超過した場合、その超過日数に `penalty_weight` を乗じた値がペナルティとして加算されます。
    -   `"soft_min"`: 従業員の総勤務日数が `days` に満たない場合、その不足日数に `penalty_weight` を乗じた値がペナルティとして加算されます。
-   **共通の注意点:**
    -   `employee_id`、`constraint_type`、`days` は必須パラメータです。いずれかが不足している場合、該当ルールはスキップされ警告が表示されます。
    -   存在しない `employee_id` が指定された場合も、該当ルールはスキップされ警告が表示されます。
    -   ソフト制約で `penalty_weight` が0以下の場合、その制約は実質的に効果がありません。
    -   非常に厳しいハード制約（例: 全従業員の勤務日数を `exact` で細かく指定）は、他の制約との間で矛盾を生じさせ、実行可能な解が見つからなくなる (INFEASIBLE) リスクを高めます。ソフト制約を適切に利用するか、ハード制約の値を慎重に設定することが推奨されます。
-   **実装状況:** 完了

### 9. 土日祝日公休ルール

-   **担当関数:** `add_weekend_holiday_constraint` (於 `src/shift_model.py`)
-   **概要:** 全ての従業員に対し、カレンダー上の土曜日、日曜日、および指定された祝日リストに基づき、これらの日を原則として「公休」に設定します。ハード制約またはソフト制約として設定可能です。
-   **設定方法:** `main` 関数内で `add_weekend_holiday_constraint` 関数を呼び出します。以下のパラメータを指定します:
    -   `model` (cp_model.CpModel): OR-Toolsのモデルオブジェクト。
    -   `variables` (dict): シフト割り当て変数。
    -   `employee_ids` (list): 対象となる全従業員のIDリスト。
    -   `dates` (list[datetime.date]): 対象期間の日付オブジェクトのリスト。
    -   `shifts` (list[str]): シフト名のリスト。
    -   `holidays_list` (list[datetime.date]): 祝日として扱う日付オブジェクトのリスト (例: `HOLIDAYS_2025_APR_MAY`)。
    -   `constraint_type` (str, optional): "hard" または "soft"。デフォルトは "hard"。
    -   `penalty_weight` (int, optional): ソフト制約の場合のペナルティの重み。`constraint_type`が`soft`でこの値が0より大きい場合に有効。

    ```python
    # main関数内での設定例 (ハード制約として土日祝を公休に)
    # weekend_holiday_penalty_terms = add_weekend_holiday_constraint(
    #     model,
    #     variables,
    #     employee_ids, 
    #     dates,
    #     SHIFTS,
    #     HOLIDAYS_2025_APR_MAY, # グローバル定数などから祝日リストを渡す
    #     constraint_type="hard"
    # )
    # all_penalty_terms.extend(weekend_holiday_penalty_terms)

    # main関数内での設定例 (ソフト制約として土日祝を公休に)
    # weekend_holiday_penalty_terms_soft = add_weekend_holiday_constraint(
    #     model,
    #     variables,
    #     employee_ids, 
    #     dates,
    #     SHIFTS,
    #     HOLIDAYS_2025_APR_MAY,
    #     constraint_type="soft",
    #     penalty_weight=50 # 土日祝に公休が取れなかった場合のペナルティ
    # )
    # all_penalty_terms.extend(weekend_holiday_penalty_terms_soft)
    ```
-   **ハード制約時 (`constraint_type="hard"`)**:
    -   全ての従業員に対し、土曜日、日曜日、および `holidays_list` に含まれる祝日は、必ず「公休」シフトが割り当てられます。
-   **ソフト制約時 (`constraint_type="soft"`)**:
    -   全ての従業員に対し、土曜日、日曜日、または `holidays_list` に含まれる祝日に「公休」シフトが割り当てられなかった場合、その違反1件につき `penalty_weight` で指定されたペナルティが課されます。
-   **共通の注意点:**
    -   この制約はデフォルトで「公休」を割り当てようとします。「公休」というシフト名が `shifts` リストに存在しない場合、エラーとなり制約は追加されません。
    -   祝日リスト (`holidays_list`) に含まれる日付が対象期間 (`dates`) 外である場合、その祝日は無視されます。
    -   ソフト制約時に `penalty_weight` が0以下の場合は、実質的に効果はありません。
    -   **この制約をハード制約として、特に全従業員を対象に適用すると、人員配置ルール等との間で矛盾が生じ、実行可能な解が見つからなくなる (INFEASIBLE) リスクが非常に高まります。** ソフト制約として利用するか、対象従業員を限定し、他の必須業務とのバランスを考慮することが強く推奨されます。
-   **実装状況:** 完了 (対象従業員指定機能追加)

### 10. 従業員ステータスに基づく全日固定シフトルール

-   **担当関数:** `add_employee_status_constraint` (於 `src/shift_model.py`)
-   **概要:** 従業員情報ファイル (`employees.csv`) に含まれる「ステータス」列の値を参照し、指定されたステータス（例: 「育休」、「病休」）に該当する従業員に対し、シフト対象期間の全日にわたり特定のシフト（デフォルトは「公休」）を割り当てるハード制約です。
-   **前提条件:**
    -   従業員情報ファイル (`employees.csv` を読み込んだ `employee_info_df`) に、「ステータス」という名称の列が存在する必要があります。
    -   この「ステータス」列に、「育休」や「病休」など、全日休暇の対象としたいステータス名が適切に設定されている必要があります。
-   **設定方法:** `main` 関数内で `add_employee_status_constraint` 関数を呼び出します。以下のパラメータを指定します:
    -   `model` (cp_model.CpModel): OR-Toolsのモデルオブジェクト。
    -   `variables` (dict): シフト割り当て変数。
    -   `employee_info_df` (pd.DataFrame): 「職員ID」と「ステータス」列を含む従業員情報DataFrame。
    -   `dates` (list[datetime.date]): 対象期間の日付オブジェクトのリスト。
    -   `shifts` (list[str]): シフト名のリスト。
    -   `status_values_for_full_leave` (list[str]): 全日休暇の対象とするステータス名のリスト (例: `["育休", "病休"]`)。
    -   `leave_shift_name` (str, optional): 休暇時に割り当てるシフト名。デフォルトは `"公休"`。

    ```python
    # main関数内での設定例
    # if employee_info_df is not None and "ステータス" in employee_info_df.columns:
    #     add_employee_status_constraint(
    #         model,
    #         variables,
    #         employee_info_df,
    #         dates,
    #         SHIFTS,
    #         status_values_for_full_leave=["育休", "病休"],
    #         leave_shift_name="公休"
    #     )
    # else:
    #     print("情報: ...従業員ステータスに基づく制約はスキップ...")
    ```
-   **動作 (ハード制約のみ):**
    -   `employee_info_df` の「ステータス」列が `status_values_for_full_leave` リスト内の一つの値に合致する各従業員について、期間 (`dates`) 中の全ての日が `leave_shift_name` で指定されたシフトに固定されます。
-   **共通の注意点:**
    -   この制約はハード制約としてのみ機能し、ペナルティ項は返しません。
    -   前提条件である「ステータス」列が `employee_info_df` に存在しない場合、または `status_values_for_full_leave` リストが空の場合、この制約は適用されず、警告または情報メッセージが表示されます。
    -   指定された `leave_shift_name` が `shifts` リストに存在しない場合、エラーとなり制約は追加されません。
    -   多数の従業員が長期間この制約の対象となると、他の人員配置ルールや制約との間で矛盾が生じ、実行可能な解が見つからなくなる (INFEASIBLE) リスクがあります。特に、休暇扱いとする従業員が多い場合は注意が必要です。
-   **実装状況:** 完了 (対象従業員指定機能追加)

## 今後の拡張・検討事項

今後、他の制約条件を追加・変更する際も、この基本設計思想に沿ってハード制約とソフト制約を選択し、ルール詳細は辞書型で渡すように実装を進めていく予定です。 

### 新しい制約 `add_weekend_holiday_constraint`

-   **担当関数:** `add_weekend_holiday_constraint` (於 `src/shift_model.py`)
-   **概要:** 週末に休日を取る従業員の数を制御する制約です。ハード制約（正確な日数、上限日数、下限日数のいずれかを指定）またはソフト制約（目標日数からの乖離、上限超過、下限不足に対してペナルティ）として設定可能です。
-   **設定方法:** `main` 関数内で、週末休日制御ルールのリスト (`weekend_holiday_rules`) を定義します。各ルールは以下のキーを持つ辞書です:
    -   `employee_id` (str): 対象となる従業員のID。
    -   `constraint_type` (str): 制約の種類。以下のいずれかを指定します:
        -   `"exact"`: 週末休日数を指定された `days` に完全に一致させます（ハード制約）。
        -   `"max"`: 週末休日数を指定された `days` 以下に制限します（ハード制約）。
        -   `"min"`: 週末休日数を指定された `days` 以上に制限します（ハード制約）。
        -   `"soft_exact"`: 週末休日数を指定された `days` に近づけます。差の絶対値に対してペナルティが課されます（ソフト制約）。
        -   `"soft_max"`: 週末休日数が指定された `days` を超えた場合に、超過分に対してペナルティが課されます（ソフト制約）。
        -   `"soft_min"`: 週末休日数が指定された `days` に満たない場合に、不足分に対してペナルティが課されます（ソフト制約）。
    -   `days` (int): 目標とする週末休日数、または上限/下限となる週末休日数。
    -   `penalty_weight` (int, optional): ソフト制約の場合のペナルティの重み。`constraint_type` がソフト制約（`soft_exact`, `soft_max`, `soft_min`）の場合に有効です。デフォルトは0。
-   **週末休日のカウント対象:** 週末休日とは土曜日と日曜日を指します。

    ```python
    # main関数内での設定例
    weekend_holiday_rules = [
        # ハード制約の例
        {"employee_id": "A001", "constraint_type": "exact", "days": 2}, # A001は週末にちょうど2日休日
        {"employee_id": "B002", "constraint_type": "max", "days": 3},   # B002は週末中最大3日休日
        {"employee_id": "C003", "constraint_type": "min", "days": 1},   # C003は週末中最低1日休日
        
        # ソフト制約の例
        # D004は週末2日休日が目標。1日ずれるごとにペナルティ5
        {"employee_id": "D004", "constraint_type": "soft_exact", "days": 2, "penalty_weight": 5},
        # E005は週末最大3日休日が目標。3日を超えると1日超過あたりペナルティ10
        {"employee_id": "E005", "constraint_type": "soft_max", "days": 3, "penalty_weight": 10},
        # F006は週末最低1日休日が目標。1日に満たないと1日不足あたりペナルティ8
        {"employee_id": "F006", "constraint_type": "soft_min", "days": 1, "penalty_weight": 8},
        
        # 同じ従業員に複数の週末休日ルールを適用することも理論上は可能ですが、
        # ルール同士が矛盾しないように注意が必要です。
        # 例えば、A001に "exact": 2 と "soft_max": 1, penalty:10 を設定すると、
        # exact=2が優先され、soft_maxルールは常にペナルティ10を発生させることになります。
    ]
    # ...
    # if employee_info_df is not None:
    #     weekend_holiday_penalty_terms = add_weekend_holiday_constraint(
    #         model,
    #         variables,
    #         employee_info_df,
    #         dates,
    #         SHIFTS,
    #         weekend_holiday_rules
    #     )
    #     all_penalty_terms.extend(weekend_holiday_penalty_terms)
    ```
-   **ハード制約時 (`constraint_type` が `"exact"`, `"max"`, `"min"`)**:
    -   `"exact"`: 従業員の週末休日数が、指定された `days` と完全に一致するように強制されます。
    -   `"max"`: 従業員の週末休日数が、指定された `days` 以下になるように強制されます。
    -   `"min"`: 従業員の週末休日数が、指定された `days` 以上になるように強制されます。
-   **ソフト制約時 (`constraint_type` が `"soft_exact"`, `"soft_max"`, `"soft_min"`)**:
    -   `"soft_exact"`: 従業員の週末休日数が `days` から乖離した場合、その差の絶対値に `penalty_weight` を乗じた値がペナルティとして加算されます。
    -   `"soft_max"`: 従業員の週末休日数が `days` を超過した場合、その超過日数に `penalty_weight` を乗じた値がペナルティとして加算されます。
    -   `"soft_min"`: 従業員の週末休日数が `days` に満たない場合、その不足日数に `penalty_weight` を乗じた値がペナルティとして加算されます。
-   **共通の注意点:**
    -   `employee_id`、`constraint_type`、`days` は必須パラメータです。いずれかが不足している場合、該当ルールはスキップされ警告が表示されます。
    -   存在しない `employee_id` が指定された場合も、該当ルールはスキップされ警告が表示されます。
    -   ソフト制約で `penalty_weight` が0以下の場合、その制約は実質的に効果がありません。
    -   非常に厳しいハード制約（例: 全従業員の週末休日数を `exact` で細かく指定）は、他の制約との間で矛盾を生じさせ、実行可能な解が見つからなくなる (INFEASIBLE) リスクを高めます。ソフト制約を適切に利用するか、ハード制約の値を慎重に設定することが推奨されます。
-   **実装状況:** 完了 (対象従業員指定機能追加) 