"""Shared Streamlit session state keys to avoid circular imports."""

# Admin console
ADMIN_VIEW_KEY = "admin_console_active"

# Help / guidance drawer
HELP_DRAWER_OPEN_KEY = "help_drawer_open"
HELP_DRAWER_SECTION_KEY = "help_drawer_section"
HELP_DRAWER_TOPIC_WIDGET_KEY = "help_drawer_topic"

# Home dataframe selection widgets — clear when leaving/returning so prior
# row clicks do not auto-reopen holding analysis.
HOME_POSITIONS_TABLE_KEY = "home_positions_table"
HOME_CLEAR_DIVIDEND_RISK_TABLE_KEY = "home_clear_dividend_risk"
HOME_TABLE_SELECTION_KEYS = (
    HOME_POSITIONS_TABLE_KEY,
    HOME_CLEAR_DIVIDEND_RISK_TABLE_KEY,
)
