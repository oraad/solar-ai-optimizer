# Shared HA Supervisor data-dir wiring for run.sh and tests.
# Override SOLAR_ADDON_DATA_ROOT / SOLAR_APP_DATA_ROOT in tests only.
_solar_data_root="${SOLAR_ADDON_DATA_ROOT:-/data}"
_solar_app_data="${SOLAR_APP_DATA_ROOT:-/app/data}"

if [ -d "$_solar_data_root" ]; then
  export DATA_DIR="$_solar_data_root"
  export DATABASE_URL="sqlite+aiosqlite:///${_solar_data_root}/solar.db"

  if [ ! -f "${_solar_data_root}/config.runtime.yaml" ] && [ -d "$_solar_app_data" ]; then
    _solar_migrated=0
    for _solar_f in config.runtime.yaml solar.db model.json runtime_state.json local_auth.env; do
      if [ -f "${_solar_app_data}/${_solar_f}" ] && [ ! -e "${_solar_data_root}/${_solar_f}" ]; then
        cp -a "${_solar_app_data}/${_solar_f}" "${_solar_data_root}/${_solar_f}"
        _solar_migrated=1
      fi
    done
    if [ "$_solar_migrated" -eq 1 ]; then
      echo "Migrated persistence from ${_solar_app_data} to ${_solar_data_root}."
    fi
  fi
fi

unset _solar_data_root _solar_app_data _solar_migrated _solar_f
