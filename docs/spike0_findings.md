# spike0 結果記録

## 環境

- Blender バージョン: **5.0.1**（リリース版、alpha ではない）
- OS: Windows 11
- 実行日: 2026-05-16
- 実行者: Yato

## 結果テーブル

| # | 検証項目 | 結果 | コメント |
|---|---|---|---|
| 1 | `blender_manifest.toml` 認識 | ✅ OK | Extensions システム経由で登録成功 |
| 2 | `draw_handler_add(POST_PIXEL)` 矩形描画 | ✅ OK | Image Editor 左下に青クワッド描画 |
| 3 | `gpu.shader.from_builtin('UNIFORM_COLOR')` | ✅ OK | 5.0.1 で組み込みシェーダ名そのまま動作 |
| 4 | `blf.draw()` font_id=0 | ✅ OK | デフォルトフォントで描画成功 |
| 5 | Modal Operator + UNDO で巻き戻る | ✅ OK | Ctrl+Z で起動前の値に戻る挙動確認 |
| 6 | Modal CANCELLED が undo に積まれない | ✅ **OK** | 後述 |
| 7 | `IMAGE_HT_header.append/remove` | ✅ OK | ヘッダ右上に "K-spike0" 表示・unregister で消える |
| 8 | `Window/Area.as_pointer()` 安定性 | ✅ OK | pointer ベースで成立、二次キーも成立 |

## (6) Modal CANCELLED 非 undo の詳細

検証手順:
1. 初期値 0 で `Run Modal (commit)` 実行 → 値を -487 に確定
2. `Run Modal (cancel only)` 実行 → 値を別の値に動かす → ESC で終了 → 値が -487 に戻る
3. `Ctrl+Z` を押す → 値が **0**（commit 前の値）に戻る

→ cancel-only Modal が undo スタックに何も積んでいないことが確認できた。Ctrl+Z 1 回で commit Modal の前まで一気に戻った = 間に cancel-only Modal のステップが入っていない。

**結論**: dry-run + apply パターンの前提（プラン v7「Modal CANCELLED 終了時にアンドゥスタックに何も積まれない」）が成立。本体の Modal Operator は素直に「Modal 中は PropertyGroup を直接書換、CANCELLED で元値復元、FINISHED で確定値を最終書込」で実装可能。

## (8) Pointer 安定性 詳細

| シナリオ | 結果 | 備考 |
|---|---|---|
| (a) 直後 | ✅ pointer 一致 + secondary も成立 | snapshot screen=Layout area_idx=3 |
| (b) Workspace 切替 → 戻る | 未検証（任意） | 必要なら後日確認 |
| (c) Area サイズ変更 | 未検証（任意） |  |
| (d) Area 分割 | ✅ pointer 一致 | スクショで複数 Area 状態でも追跡成立 |
| (e) Image Editor 閉じる→別 Area で再 ON | 未検証（任意） |  |

→ pointer は **session 中は安定**との仮判定。本体実装では **一次キー pointer**、**二次キー (screen 名 + area index)** の 2 層を用意するが、通常運用では一次キーで足りる見込み。

## 採用 fallback

NG 項目が無かったため、プラン v7 の fallback 設計は **どれも採用不要**。当初設計どおりに alpha1 を進める。

## spike0 で判明した spike 外の知見

1. **Blender 5.0.1 はリリース版**（プランでは "5.x alpha 想定" と書いていたが実際は安定版）。manifest 周りは安定運用前提で書ける
2. **Extensions パス（`extensions/user_default/`）必須**。dev_install スクリプトはこれを反映済み
3. **userpref.blend の更新日時で現役判定**しないと、PowerShell の `Sort-Object | Select -First 1` で誤判定する罠あり（Yato さんは APPDATA に 5.0 と 5.1 両方ある）

## 次フェーズ（alpha1）への影響

- 設計プラン v7 をそのまま採用
- 描画ホスト方針を v7 から微修正: **専用 Workspace "Kinema" を append し、その中身に Image Editor を仕込む** ことでユーザーは普段のレイアウトを汚されない（技術的には Image Editor 流用のまま）
- Modal Operator の dry-run+apply 採用が確定
- pointer 識別子は一次キー単独で書き始め、(b)(c)(e) で問題が出たら二次キー fallback を有効化
