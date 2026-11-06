import XCTest
import Foundation

/// Regression: tapping Save in a Form must not invoke the Generate action.
final class KeyManagerUITests: XCTestCase {
    override func setUpWithError() throws { continueAfterFailure = false }

    func testSavingTypedKeyDoesNotGenerateAnotherKey() throws {
        let app = XCUIApplication()
        let name = "key-regression-" + String(UUID().uuidString.prefix(8))
        let expected = String(repeating: "01234567", count: 16)
        app.launch()
        openManager(app)

        let nameField = app.textFields["key.name"]
        XCTAssertTrue(nameField.waitForExistence(timeout: 10))
        nameField.tap(); nameField.typeText(name)
        let keyField = app.secureTextFields["key.value"]
        keyField.tap(); keyField.typeText(expected)
        let keyboardDone = app.buttons["key.keyboardDone"]
        if keyboardDone.waitForExistence(timeout: 3) { keyboardDone.tap() }
        let save = app.buttons["key.save"]
        for _ in 0..<6 { if save.isHittable { break }; keyForm(app).swipeUp() }
        XCTAssertTrue(save.isHittable, "Save button must be reachable after dismissing the keyboard")
        save.tap()
        // Assert on the actual stored record. A success notice inserted below
        // the keyboard can be outside the Form's visible accessibility tree.
        reveal(app, name: name)
        XCTAssertEqual(app.staticTexts["key.revealed"].label, expected)

        // Verify the persisted record, rather than only the current form state.
        app.terminate(); app.launch()
        openManager(app)
        let reload = app.buttons["key.reload"]
        XCTAssertTrue(reload.waitForExistence(timeout: 5))
        reload.tap()
        XCTAssertTrue(app.staticTexts["key.reloaded"].waitForExistence(timeout: 5), "A single tap on Refresh must show its result")
        reveal(app, name: name)
        XCTAssertEqual(app.staticTexts["key.revealed"].label, expected)
    }

    private func openManager(_ app: XCUIApplication) {
        let button = app.buttons["keyManager.open"]
        XCTAssertTrue(button.waitForExistence(timeout: 10))
        XCTAssertFalse(app.alerts.firstMatch.exists, "App launch failed: " + failureDetails(app))
        button.tap()
    }
    private func reveal(_ app: XCUIApplication, name: String) {
        let menu = app.buttons["key.actions." + name]
        for _ in 0..<8 {
            if menu.exists && menuIsVisible(menu, in: app) { break }
            keyForm(app).swipeDown()
        }
        XCTAssertTrue(menu.exists && menuIsVisible(menu, in: app), "Saved key menu must be visible. " + failureDetails(app))
        // SwiftUI Menu exposes a wrapper Button with a valid frame but may
        // report AXVisiblePoint=(-1,-1) even when visibly on-screen (Xcode 16.4).
        // Prefer its native trigger; otherwise tap the verified visible frame.
        let trigger = menu.buttons.firstMatch
        if trigger.exists && trigger.isHittable { trigger.tap() }
        else if menu.isHittable { menu.tap() }
        else { menu.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap() }
        let viewKey = app.buttons["查看密钥"]
        XCTAssertTrue(viewKey.waitForExistence(timeout: 5), "Tapping the visible menu must open its actions")
        viewKey.tap()
        XCTAssertTrue(app.staticTexts["key.revealed"].waitForExistence(timeout: 10))
    }
    private func menuIsVisible(_ menu: XCUIElement, in app: XCUIApplication) -> Bool {
        let frame = menu.frame
        let visible = keyForm(app).frame.intersection(app.frame)
        return frame.width > 0 && frame.height > 0 && visible.contains(frame)
    }
    private func keyForm(_ app: XCUIApplication) -> XCUIElement {
        let form = app.descendants(matching: .any).matching(identifier: "key.form").firstMatch
        XCTAssertTrue(form.exists, "Scroll within the key form, not the whole application sheet")
        return form
    }
    private func failureDetails(_ app: XCUIApplication) -> String {
        let alert = app.alerts.firstMatch
        if alert.exists { return alert.staticTexts.allElementsBoundByIndex.map(\.label).joined(separator: " | ") }
        let error = app.staticTexts["key.error"]
        if error.exists { return error.label }
        return "No error banner or alert. Verify the saved-key row and keyboard state in the xcresult screenshot."
    }
}
