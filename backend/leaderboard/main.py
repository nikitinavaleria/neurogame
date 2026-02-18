from pathlib import Path
import sys

import streamlit as st

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import load_settings
from app.leaderboard import build_leaderboard

st.set_page_config(page_title="NeuroGame Leaderboard", layout="wide")
settings = load_settings()

st.title("NeuroGame Leaderboard")
st.caption("Рейтинг игроков по точности, уровню и скорости реакции")

col1, col2, col3 = st.columns([1, 1, 2])
with col1:
    limit = st.number_input("Лимит строк", min_value=10, max_value=500, value=100, step=10)
with col2:
    min_tasks = st.number_input("Мин. задач", min_value=0, max_value=5000, value=30, step=10)
with col3:
    search_user = st.text_input("Найти пользователя", value="", placeholder="user_id")

rows = build_leaderboard(Path(settings.db_path), limit=int(limit), min_tasks=int(min_tasks))

if not rows:
    st.warning("Пока нет данных для лидерборда.")
    st.stop()

if search_user.strip():
    normalized = search_user.strip().lower()
    found = [r for r in rows if str(r.get("user_id", "")).lower() == normalized]
    if found:
        user = found[0]
        st.success(
            f"Пользователь {user['user_id']}: ранг #{user['rank']}, score={user['score']}, "
            f"уровень={user['best_level']}, точность={user['accuracy_pct']}%"
        )
    else:
        st.info("Пользователь не найден в текущем срезе.")

st.dataframe(rows, use_container_width=True, hide_index=True)
st.caption(f"Источник данных: {settings.db_path}")
