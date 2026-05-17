# beta1 Shot Timeline 動作確認手順

beta1 では **Video Sequencer (VSE) を kinema 専用タイムラインビューに転用** する独自 UI 基盤を実装した。Premiere 風の Shot ストリップ表示と、shot_dispatcher による `scene.camera` 自動切替が動作する。

> kinema モード ON 時、ホスト Sequencer の WINDOW Region は kinema 側で塗り潰されるため、標準 VSE ストリップの表示は隠れる。Sequencer の View Type は **"Sequencer"** に切り替えておくこと（Preview ではなく）。

## 1. インストール / 再有効化

```powershell
cd C:\Work\Yato\Claude\kinema\scripts
.\dev_install.ps1 -BlenderVersion "5.0"
```

新規 Operator / PropertyGroup（`WindowManager.kinema`）が追加されているので **Blender 再起動 or Disable→Enable 必須**。

## 2. シーン準備

1. Properties > Scene > Kinema パネルの **Quick Start** を 2〜3 回押す
   → `Sample_Camera`, `Sample_Camera_001`, `Sample_Camera_002` が出来る
2. それぞれを Load → Instance に 2〜3 件

## 3. タイムラインビュー起動

1. 任意のエリアを **Video Sequencer** に切り替える（左上アイコン → "ビデオシーケンサー" / "Video Sequencer"）
2. Sequencer の View Type は **"Sequencer"** に（"Preview" や "Sequencer & Preview" ではなく）
3. Sequencer ヘッダ右側に **"Kinema"** ボタンが出ているのでクリック
   - 押すとそのエリアが kinema タイムラインビューになる
   - ヘッダの表記が "Kinema Timeline" + [Add Shot] [X] になる
4. WINDOW Region が暗い背景 + 横方向にフレーム目盛り + 横線（トラック）で塗り替えられる

> 複数の Sequencer を開いていても、kinema 化されるのは **押した 1 つだけ**。他の Sequencer は標準動作のまま。

## 4. Shot を追加

方法 A: タイムラインビューのヘッダの **Add Shot** ボタン
方法 B: Properties > Scene > Kinema の Shot Timeline セクションの **Add Shot** ボタン

どちらでもプレイヘッドのフレーム位置から **50 フレーム**分の Shot がタイムラインに追加される。

色付きの矩形（ストリップ）が描かれていれば OK。

## 5. プレイヘッド移動

タイムラインビューの **下マージン**（フレーム番号目盛りの位置）を **左クリック** すると、その x 座標に対応するフレームに `scene.frame_current` がジャンプ。

## 6. Shot 選択

ストリップ本体を **左クリック** すると `active_clip_uid` が更新され、Properties > Scene > Kinema の Shot Timeline 一覧でドット (●) が付く行になる。

## 7. 再生で `scene.camera` 切替

1. Shot を 2 つ作って、`active_instance_index` を切り替えながら追加し、それぞれ違うカメラを参照させる
2. プレイヘッドを最初の Shot 範囲内に移動 → そのカメラが scene.camera に
3. プレイヘッドを 2 つ目の Shot 範囲内に移動 → カメラが切替
4. **再生** → 自動的に Shot 境界で切替

## 8. Shot 削除

Properties > Scene > Kinema の Shot Timeline セクションの:
- **X ボタン**: 選択中の Shot を削除
- **Clear All**: 全 Shot を削除

## 9. タイムラインモード OFF

タイムラインビュー ヘッダの **X ボタン** で OFF。Sequencer が標準表示に戻る。

## 10. 確認したい挙動チェックリスト

- [ ] Video Sequencer のヘッダに "Kinema" ボタンが出る
- [ ] クリックで kinema タイムラインビューが起動、暗い背景 + グリッド + トラック描画
- [ ] 他の Sequencer を開いてもそちらは標準動作のまま
- [ ] Add Shot で Shot ストリップが描画される
- [ ] 下マージンクリックで `scene.frame_current` が変わる
- [ ] ストリップクリックで active_clip_uid が変わる（一覧でドットが移動）
- [ ] プレイヘッドが Shot 範囲内に入ると scene.camera がその Shot のカメラに切替
- [ ] 再生でも Shot 境界で切替
- [ ] タイムラインモード OFF で Sequencer が標準表示に戻る
- [ ] Workspace 切替して戻ってもタイムラインビューが復帰する（pointer or 二次キーで自己修復）

## beta2 で実装予定

- ドラッグでストリップ移動
- 端ドラッグでトリム
- K キーでカット
- ボックス選択 / 複数選択
- ホイールでズーム
- Workspace 用キーマップ stack
