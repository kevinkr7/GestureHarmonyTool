module com.harmony.gestureharmonytoolui {
    requires javafx.controls;
    requires javafx.fxml;
    requires javafx.web;


    opens com.harmony.gestureharmonytoolui to javafx.fxml;
    exports com.harmony.gestureharmonytoolui;
}