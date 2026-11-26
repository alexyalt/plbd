def menu(request):
    return {
        "menu": [
            ("dashboard", "Главная"),
            ("inspection_list", "Осмотры"),
            ("treatment_list", "Обработки"),
            ("writeoff", "Списание ТМЦ"),
            ("reports", "Отчёты"),
            ("protection", "График защиты"),
            ("catalogs", "Справочники"),
            ("tools", "Сервис"),
        ]
    }
