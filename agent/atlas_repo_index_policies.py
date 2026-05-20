from __future__ import annotations
POLICIES={
'repo_index_v1':{'allow_build':True,'allow_incremental_update':True,'allow_status_only':True,'allow_scan_hidden_dirs':False,'allow_scan_vendor_dirs':False,'allow_shell_commands':False,'allow_remote_git':False,'max_files':5000,'max_file_bytes':1_000_000,'supported_extensions':['.py','.js','.ts','.tsx','.jsx','.html','.css','.json','.md','.yaml','.yml','.toml'],'exclude_dirs':['.git','node_modules','venv','.venv','__pycache__','dist','build','.pytest_cache','.mypy_cache','ca_data','models','.cache']},
'repo_index_strict_v1':{'allow_build':True,'allow_incremental_update':True,'allow_status_only':True,'allow_scan_hidden_dirs':False,'allow_scan_vendor_dirs':False,'allow_shell_commands':False,'allow_remote_git':False,'max_files':2000,'max_file_bytes':500_000,'include_ui_events':False,'include_routes':True},
'repo_index_status_only_v1':{'allow_build':False,'allow_incremental_update':False,'allow_status_only':True,'no_scanning':True},
}
