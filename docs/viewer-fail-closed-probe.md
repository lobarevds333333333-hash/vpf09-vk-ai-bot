# Viewer fail-closed probe

Временный PR проверяет, что отсутствие `APIHOST_API_KEY` создаёт неуспешный
Check Run для точного head SHA и не позволяет считать review пройденным.
