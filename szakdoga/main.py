import sqlite3
import sys
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import Qt, pyqtSignal, QObject
from PyQt5.QtGui import QIcon, QMovie
from PyQt5.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox
from PyQt5.uic import loadUi
from ultralytics import YOLO


class LoadingScreen(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        # A betöltőképernyő inicializálása és beállítása
        self.setFixedSize(200, 200)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.CustomizeWindowHint)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)

        self.label_animation = QtWidgets.QLabel()
        self.movie = QMovie('Loading_2.gif')
        self.label_animation.setMovie(self.movie)
        self.movie.start()

        layout.addWidget(self.label_animation)


def show_warning_messagebox():
    # Figyelmeztető üzenet megjelenítése, ha nem találhatóak objektumok a képen
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Warning)
    msg.setText("Nem sikerült semmit sem észlelni a képen.")
    msg.setWindowTitle("Figyelem")
    msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
    msg.exec_()


class AnalysisWorker(QObject):
    finished = pyqtSignal(str)
    no_object_detected = pyqtSignal()

    def __init__(self, file, model):
        super().__init__()
        self.file = file
        self.model = model

    def run(self):
        results = self.model.predict(source=self.file, conf=0.5)
        for result in results:
            if result.boxes:
                box = result.boxes[0]
                class_id = int(box.cls)
                object_name = self.model.names[class_id]
                self.finished.emit(object_name)
                return
        self.no_object_detected.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        # Főablak inicializálása és felület betöltése
        self.model = YOLO('best.pt')
        loadUi("gui.ui", self)
        self.recipes = []
        self.current_recipe_index = 0
        self.current_tip_index = 0
        self.file = ""
        self.tips.setReadOnly(True)
        self.showRecipe.setEnabled(False)
        self.tip = ["     Törekedj arra, hogy minél pontosabb képet csinálj a hozzávalóról.",
                    "     A legjobb eredmények érdekében feldolgozatlan állapotban fotózd le a hozzávalót.",
                    "     Megfelelő fényviszonyok között pontosabb lesz az elemzés.",
                    ]

        # Gombok ikonjai
        self.scrollTips.setStyleSheet("image: url(resources/images/arrow.png);background-color: rgb(66, 94, 121);")
        self.browse.setStyleSheet("image : url(resources/images/files.png);background-color: rgb(66, 94, 121);")
        self.showRecipe.setStyleSheet("image : url(resources/images/cook.png);background-color: rgb(66, 94, 121);")
        self.analyze.setStyleSheet("image : url(resources/images/start.png);background-color: rgb(66, 94, 121);")

        # Gombok funkcióval való ellátása
        self.browse.clicked.connect(self.browse_files)
        if self.recipeTitle.text() == "":
            self.prevRecipe.setEnabled(False)
            self.nextRecipe.setEnabled(False)
        self.prevRecipe.clicked.connect(self.show_previous_recipe)
        self.nextRecipe.clicked.connect(self.show_next_recipe)
        self.tips.setText(self.tip[self.current_tip_index])
        self.scrollTips.clicked.connect(self.next_string)
        self.analyze.clicked.connect(self.analyze_image)
        self.showRecipe.clicked.connect(lambda: self.fetch_recipe(self.scannedObject.text()))

    # Fájlok böngészése
    def browse_files(self):
        fname = QFileDialog.getOpenFileName(self, 'Open file', 'C:/Users', 'Images (*.png, *.xmp *.jpg)')
        self.filename.setText(fname[0])

    # Tippek közötti lapozgatás
    def next_string(self):
        self.current_tip_index = (self.current_tip_index + 1) % len(self.tip)
        self.tips.setText(self.tip[self.current_tip_index])

    def analyze_image(self):
        self.file = self.filename.text()
        if not self.file:
            show_warning_messagebox()
            return

        self.loading_screen = LoadingScreen()
        self.loading_screen.show()

        self.thread = QtCore.QThread()
        self.worker = AnalysisWorker(self.file, self.model)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_analysis_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.no_object_detected.connect(self.on_no_object_detected)
        self.worker.no_object_detected.connect(self.thread.quit)
        self.worker.no_object_detected.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()

    def on_analysis_finished(self, object_name):
        self.scannedObject.setText(object_name)
        self.showRecipe.setEnabled(True)
        self.prevRecipe.setEnabled(False)
        self.nextRecipe.setEnabled(False)
        self.recipes.clear()
        self.recipeTitle.setText("")
        self.ingredients.setText("")
        self.instructions.setText("")
        self.loading_screen.close()

    def on_no_object_detected(self):
        self.loading_screen.close()
        show_warning_messagebox()

    def fetch_recipe(self, ingredient):
        # Receptek lekérése a megadott hozzávaló alapján az adatbázisból
        connection = sqlite3.connect("food.db")  # Adatbázis megnyitása
        cursor = connection.cursor()
        self.current_recipe_index = 0

        query2 = """
            SELECT recipes.name, GROUP_CONCAT(ingredients.name_hu || ': ' || recipe_ingredients.quantity, ', \n'), recipes.instructions
            FROM recipes
            JOIN recipe_ingredients ON recipes.id = recipe_ingredients.recipe_id
            JOIN ingredients ON recipe_ingredients.ingredient_id = ingredients.id
            WHERE recipes.id IN (
                SELECT recipe_id
                FROM recipe_ingredients
                JOIN ingredients ON recipe_ingredients.ingredient_id = ingredients.id
                WHERE ingredients.name = ?
            )
            GROUP BY recipes.id
        """
        cursor.execute(query2, (ingredient,))
        self.recipes = cursor.fetchall()
        self.show_current_recipe()
        connection.close()  # Adatbázis bezárása

    def show_current_recipe(self):
        # Jelenlegi recept megjelenítése az ablakon
        recipe = self.recipes[self.current_recipe_index]
        self.recipeTitle.setText(recipe[0])
        self.ingredients.setText("Hozzávalók: \n" + recipe[1])
        self.instructions.setText("Elkészítési útmutató: \n" + recipe[2])
        self.prevRecipe.setEnabled(True)
        self.nextRecipe.setEnabled(True)

    def show_previous_recipe(self):
        if self.current_recipe_index > 0:
            self.current_recipe_index -= 1
            self.show_current_recipe()

    def show_next_recipe(self):
        if self.current_recipe_index < len(self.recipes) - 1:
            self.current_recipe_index += 1
            self.show_current_recipe()


app = QApplication(sys.argv)
# Alkalmazás nevének és ikonjának beállítása
app.setApplicationName("Foodee")
app.setWindowIcon(QIcon('logo.png'))
mainwindow = MainWindow()
widget = QtWidgets.QStackedWidget()
widget.addWidget(mainwindow)
widget.setFixedWidth(901)
widget.setFixedHeight(600)
widget.show()
sys.exit(app.exec_())
