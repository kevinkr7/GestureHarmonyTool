module com.harmony.gestureharmonytoolui {
    requires javafx.controls;
    requires javafx.fxml;
    requires javafx.swing;
    requires java.desktop;
    requires opencv;

    opens com.harmony.gestureharmonytoolui to javafx.fxml;
    exports com.harmony.gestureharmonytoolui;
}
