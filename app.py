from poza.db import init_db
from poza.gui_qt import main

if __name__ == "__main__":
    init_db()   # Crea tablas y seed si es la primera ejecución
    main()
