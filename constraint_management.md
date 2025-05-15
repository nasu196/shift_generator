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

---

今後、他の制約条件を追加・変更する際も、この基本設計思想に沿ってハード制約とソフト制約を選択し、ルール詳細は辞書型で渡すように実装を進めていく予定です。 