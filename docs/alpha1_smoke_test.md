# alpha1 動作確認手順

## 前提

- spike0 が 8/8 OK で完了している（[spike0_findings.md](spike0_findings.md)）
- Blender 5.0.1 を使用

## 1. インストール

```powershell
cd C:\Work\Yato\Claude\kinema\scripts
.\dev_install.ps1 -BlenderVersion "5.0"
```

すでに spike0 が入っている状態でも独立してインストールされる（spike0 = `kinema_spike0`、本体 = `kinema`）。

## 2. Blender 起動 → アドオン有効化

1. Blender 5.0 を **完全終了 → 起動**（manifest は起動時のみスキャンされるため）
2. `Edit > Preferences > Add-ons` で "Kinema" を検索 → 有効化

## 3. パネルの確認

`Properties エディタ > Scene プロパティ > Kinema` セクションが出ているか。

### cineflow が enabled なら

Settings ボックスに **赤い警告バナー**が出る:

```
⚠ cineflow が enabled です
   kinema の frame_change handler は待機中
   [Disable cineflow & enable kinema handlers]
```

ボタンを押すと cineflow が無効化され、kinema の handler が有効化される。

## 4. Workspace 作成

`Workspace` ボックスの **Create Kinema Workspace** ボタンを押す。

→ Blender の上部タブに `Kinema` が追加される（普段の Layout / Modeling は触られない）。

alpha1 では Kinema タブの中身は「Layout 複製のまま」。beta1 で独自タイムライン UI を仕込む。

## 5. プリセット階層を準備（ワンクリックでも手動でも OK）

### ワンクリック（推奨）

Preset Root が存在しない / 空の時は、パネルに **Quick Start バナー**が出る:

```
▶ Quick Start
  Preset Root 'Kinema_Presets' が未準備です

  [ Quick Start ]                  ← これ 1 ボタンで Root + サンプルプリセット
  [ Init Root ] [ Capture View ]
  [ Add Selected Cameras ]
```

- **Quick Start**: `Kinema_Presets` コレクションを作り、空の場合は `Sample_Camera` サブコレクション + 新規カメラを 1 件作る。続けて自動スキャン
- **Init Root**: 空の Preset Root だけ作る（中身は自分で）
- **Capture View**: 現在の 3D ビュー視点で新規カメラを作って Preset 登録
- **Add Selected Cameras**: シーン内で選択中の Camera を Preset 登録

Quick Start を一度押せば、その後のフローは「Scan 済 → 選択 → Load」のみ。

### 手動で組みたい場合

シーン直下にコレクションを作り、その中に Camera を含むサブコレクションを置く：

```
シーンコレクション
└── Kinema_Presets           ← Source ボックスの "Preset Root" と一致する名前
    ├── Hero_Wide            ← 任意のサブコレクション
    │   └── Camera.001
    ├── Hero_CloseUp
    │   └── Camera.002
    └── Insert_Top
        └── Camera.003
```

- コレクション名に `_` が含まれていれば、最初の `_` でグループ化される
  - `Hero_Wide` / `Hero_CloseUp` → "Hero" グループ
- カスタムプロパティで設定可能なメタ:
  - `kn_default_lens` (float): デフォルト焦点距離
  - `kn_tags` (str): カンマ区切りタグ（例: `"Cinematic, Hero"`）

## 6. プリセットスキャン

Properties > Scene > Kinema パネルの **Presets ボックス**で:

1. **更新アイコン**（フォルダの右の Refresh）を押す → Scan Presets が走る
2. プリセット一覧に上記コレクションが出る
3. Hero グループは 2 件あるので **グループヘッダ** "Hero" 行が挿入される

## 7. プリセットロード

プリセットを 1 つ選択（Hero グループ内の Hero_Wide など）→ **Load Selected Preset** をクリック。

→ シーン直下に `Kinema_Instances` コレクションが作られ、その下に `Hero_Wide` のコピーが追加される（重複時は `Hero_Wide_001` で採番）。

Instances ボックスにエントリが 1 行表示される。

## 8. インスタンス操作

Instance を選択した状態で:

- **Lens (mm) スライダー** → 値を変えて **チェックアイコン**を押すと、カメラの焦点距離が即時反映
- **Preview Camera ボタン**（インスタンス行の右、目アイコン）→ `scene.camera` が切り替わる
- **Unload ボタン**（X アイコン）→ そのインスタンスを削除

## 9. Follow / LookAt / Noise

Active Instance ボックスの下に:

- **Follow** セクション → Target に Cube などを指定 → distance/height/side/damping を調整 → 再生で追従を確認
- **LookAt** セクション → Target に Empty などを指定 → damping → 再生で見つめ続けることを確認
- **Noise** チェック → strength / frequency / seed → 手振れノイズ

スクラブ / フレームジャンプ時はスナップ（damping を無視）。

## 10. Refresh

Outliner でインスタンスのコレクションを直接削除 → Properties > Scene > Kinema の **Refresh アイコン**（Instances ボックス）を押すと、参照切れのエントリが掃除される。

## 11. アンインストール

```powershell
cd C:\Work\Yato\Claude\kinema\scripts
.\dev_uninstall.ps1 -BlenderVersion "5.0"
```

## 12. 確認したい挙動チェックリスト

- [ ] Preferences で Kinema が有効化できる
- [ ] cineflow が enabled だと警告が出て、ボタン 1 つで切替できる
- [ ] Properties > Scene > Kinema パネルが描画される
- [ ] Create Kinema Workspace で `Kinema` タブが追加される
- [ ] Preset Root が無いと Quick Start バナーが出る
- [ ] Quick Start ボタン 1 回で Preset Root + サンプルカメラが揃って Scan 済になる
- [ ] Capture View で現在のビューポート視点から新規カメラが Preset 登録される
- [ ] Add Selected Cameras で選択中の Camera が Preset 登録される
- [ ] Scan Presets でコレクションが一覧表示される
- [ ] グループ（同プレフィックスが ≥2 件）でヘッダ行が出る
- [ ] Load Selected Preset で Instance が複製される（重複時は `_001` で採番）
- [ ] Lens スライダー → Apply で実カメラの lens が変わる
- [ ] Preview Camera で scene.camera が切り替わる
- [ ] Follow Target を指定 → 再生でカメラが後方追従
- [ ] LookAt Target を指定 → 再生でカメラが target を向く
- [ ] Noise ON → 手振れがかかる
- [ ] Refresh Instances で参照切れエントリが掃除される
- [ ] Unload で Instance が削除される
- [ ] Remove Kinema Workspace で Workspace タブが消える
- [ ] Disable→Enable を 3 回繰り返しても frame_change_pre に kinema_frame_change_pre が 1 つだけ
