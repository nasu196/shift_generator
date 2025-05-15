import os
import datetime
import pandas as pd

# 定数定義
OUTPUT_DIR = "results"  # プロジェクトルートからの相対パス
FILENAME_PREFIX = "shift"
# 曜日表示用
WEEKDAY_JP = ["月", "火", "水", "木", "金", "土", "日"]

# 集計列の定義 (shift_20250410_v105.csv の形式に合わせる)
AGGREGATION_COL_NAMES = {
    "公休": "集計:公休",
    "祝日": "集計:祝日",  # このロジックは今回は単純に0または空
    "日勤": "集計:日勤",
    "早出": "集計:早出",
    "夜勤": "集計:夜勤",
    "明勤": "集計:明勤",
}


def save_results_to_csv(
    assigned_shifts_df: pd.DataFrame, 
    employee_info_df: pd.DataFrame, 
    all_dates: list[datetime.date], 
    holidays: list[datetime.date],
    all_shift_types: list[str], # SHIFTS定数そのまま
    shifts_for_personal_aggregation: list[str], # SHIFTS_FOR_AGGREGATION定数
    working_shifts_for_daily_total: list[str] # WORKING_SHIFTS_FOR_DAILY_TOTAL定数
):
    """
    整形されたシフト結果を、指定された詳細形式でCSVファイルとして保存します。
    職員情報、曜日・祝日行、個人別集計、日付別集計を含みます。
    """
    if assigned_shifts_df is None or employee_info_df is None:
        print("エラー: save_results_to_csv に無効なDataFrameが渡されました。")
        return

    # 0. ファイル名と出力パスの準備
    start_date_for_filename = all_dates[0]
    if not os.path.exists(OUTPUT_DIR):
        try:
            os.makedirs(OUTPUT_DIR)
            print(f"'{OUTPUT_DIR}'フォルダを作成しました。")
        except OSError as e:
            print(f"エラー: '{OUTPUT_DIR}' フォルダの作成に失敗しました: {e}")
            return
    output_filename = f"{OUTPUT_DIR}/{FILENAME_PREFIX}_{start_date_for_filename.strftime('%Y%m%d')}_v01.csv"

    # 1. 割り当て結果と従業員情報をマージ (職員IDをキー)
    # assigned_shifts_dfのインデックスは既に「職員ID」のはず
    merged_df = pd.merge(employee_info_df, assigned_shifts_df, on="職員ID", how="left")    
    
    # 2. 個人別集計列の追加
    # 集計列の順序を定義 (shift_20250410_v105.csv に合わせる)
    personal_agg_cols_ordered = [
        AGGREGATION_COL_NAMES["公休"],
        AGGREGATION_COL_NAMES["祝日"],
        AGGREGATION_COL_NAMES["日勤"],
        AGGREGATION_COL_NAMES["早出"],
        AGGREGATION_COL_NAMES["夜勤"],
        AGGREGATION_COL_NAMES["明勤"]
    ]

    for shift_name in shifts_for_personal_aggregation: # 例: ["公休", "日勤", ...]
        col_name = AGGREGATION_COL_NAMES.get(shift_name)
        if col_name:
            merged_df[col_name] = merged_df[[d.strftime("%Y-%m-%d") for d in all_dates]].apply(
                lambda row: (row == shift_name).sum(), axis=1
            )
    # 「集計:祝日」列を空（または0）で作成 (ロジックは未実装のため)
    if AGGREGATION_COL_NAMES["祝日"] not in merged_df.columns:
         merged_df[AGGREGATION_COL_NAMES["祝日"]] = 0 # または "" や np.nan

    # 列の並び替え: 職員名, 担当フロア, 日付..., 個人集計列...
    date_cols_str = [d.strftime("%Y-%m-%d") for d in all_dates]
    final_ordered_columns = ["職員名", "担当フロア"] + date_cols_str + personal_agg_cols_ordered
    # 存在しない集計列がpersonal_agg_cols_orderedに含まれている場合エラーになるのでフィルタリング
    valid_personal_agg_cols = [col for col in personal_agg_cols_ordered if col in merged_df.columns]
    final_ordered_columns = ["職員名", "担当フロア"] + date_cols_str + valid_personal_agg_cols
    merged_df = merged_df[final_ordered_columns]

    # 3. 曜日・祝日行のデータを作成
    weekday_row_data = {"職員名": "", "担当フロア": ""}
    for date_obj in all_dates:
        date_str = date_obj.strftime("%Y-%m-%d")
        day_name = WEEKDAY_JP[date_obj.weekday()]
        is_holiday = "(祝)" if date_obj in holidays else ""
        weekday_row_data[date_str] = f"{day_name}{is_holiday}"
    for agg_col in valid_personal_agg_cols: # 集計列部分は空欄
        weekday_row_data[agg_col] = ""
    # weekday_row_df = pd.DataFrame([weekday_row_data], columns=final_ordered_columns) # DataFrameにする必要はない

    # 4. 日付別集計行のデータを作成
    daily_totals_rows = []
    for shift_to_total in working_shifts_for_daily_total:
        total_row_data = {"職員名": f"{shift_to_total}合計", "担当フロア": ""}
        for date_str in date_cols_str:
            total_row_data[date_str] = (merged_df[date_str] == shift_to_total).sum()
        for agg_col in valid_personal_agg_cols: # 集計列部分は空欄
            total_row_data[agg_col] = ""
        daily_totals_rows.append(total_row_data)
    # daily_totals_df = pd.DataFrame(daily_totals_rows, columns=final_ordered_columns) # DataFrameにする必要はない

    # 5. CSVファイルへの書き込み (追記方式)
    try:
        with open(output_filename, 'w', encoding='utf-8-sig', newline='') as f:
            # ヘッダー行書き込み (final_ordered_columns をカンマ区切りで)
            f.write(",".join(final_ordered_columns) + "\n")
            
            # 曜日・祝日行書き込み
            # weekday_row_values は final_ordered_columns の順序で値を取得
            weekday_row_values = [weekday_row_data.get(col, "") for col in final_ordered_columns]
            f.write(",".join(map(str, weekday_row_values)) + "\n")

            # データ行書き込み (merged_df)
            # index=False, header=False で merged_df の値をそのまま書き出す
            # merged_df の列の順序は final_ordered_columns に従っているはず
            merged_df.to_csv(f, header=False, index=False)
            
            # 日付別集計行書き込み
            for total_row_dict in daily_totals_rows:
                total_row_values = [total_row_dict.get(col, "") for col in final_ordered_columns]
                f.write(",".join(map(str, total_row_values)) + "\n")

        print(f"シフト表を '{output_filename}' に出力しました。")
    except Exception as e:
        print(f"エラー: CSVファイル '{output_filename}' への書き込み中に問題が発生しました: {e}") 