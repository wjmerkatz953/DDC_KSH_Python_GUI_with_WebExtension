from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# hanja 라이브러리의 모든 데이터 파일과 하위 모듈을 수집
datas = collect_data_files('hanja')
hiddenimports = collect_submodules('hanja')