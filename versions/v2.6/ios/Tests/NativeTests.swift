import XCTest
import UIKit
@testable import binary_image_passcode

final class NativeTests: XCTestCase {
    let key = String(repeating: "01234567", count: 16)
    func fixture(_ name: String) throws -> Data {
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: name, withExtension: nil, subdirectory: "Fixtures"))
        return try Data(contentsOf: url)
    }
    func testPythonTextFixture() throws {
        let r = try XCTUnwrap(BIPService.decrypt(fixture("text.png"), key: key, progress: { _, _ in true }))
        XCTAssertEqual(r.text, "Hello, iOS! 繁體 日本語 한국어 3132 \\u literal.\n")
        XCTAssertEqual(r.seconds, 1793701842)
    }
    func testPythonImageFixtures() throws {
        for ext in ["jpg", "png"] {
            let r = try XCTUnwrap(BIPService.decrypt(fixture("encoded_\(ext).png"), key: key, progress: { _, _ in true }))
            XCTAssertEqual(r.secretData, try fixture("secret.\(ext)"))
            XCTAssertEqual(r.png, ext == "png")
            XCTAssertEqual(r.seconds, 1793701842)
        }
    }
    func testNativeImageRoundTrips() throws {
        for png in [false, true] {
            let r = try XCTUnwrap(BIPService.encrypt(fixture("carrier.png"), secret: fixture("secret.png"), text: "", key: key, png: png, strong: false, progress: { _, _ in true }))
            let d = try XCTUnwrap(BIPService.decrypt(try XCTUnwrap(r.carrierPNG), key: key, progress: { _, _ in true }))
            XCTAssertEqual(d.secretData, r.secretData)
            XCTAssertEqual(d.seconds, r.seconds)
            XCTAssertNotNil(UIImage(data: try XCTUnwrap(d.secretData)))
        }
    }
    func testNativeTextRoundTripAndLimits() throws {
        let text = "AbZ 3132 ., \\u |漢字\n"
        let r = try XCTUnwrap(BIPService.encrypt(fixture("carrier.png"), secret: nil, text: text, key: key, png: false, strong: true, progress: { _, _ in true }))
        let d = try XCTUnwrap(BIPService.decrypt(try XCTUnwrap(r.carrierPNG), key: key, progress: { _, _ in true }))
        XCTAssertEqual(d.text, text)
        XCTAssertEqual(try TextCodec.count(String(repeating: "a", count: 60000)), 60000)
        XCTAssertThrowsError(try TextCodec.count(String(repeating: "a", count: 60001)))
        XCTAssertThrowsError(try TextCodec.count("😀"))
    }
    func testAuthenticationAndCancellation() throws {
        XCTAssertThrowsError(try BIPService.decrypt(fixture("text.png"), key: String(repeating: "9", count: 128), progress: { _, _ in true }))
        XCTAssertThrowsError(try BIPService.encrypt(fixture("carrier.png"), secret: nil, text: "cancel", key: key, png: false, strong: false, progress: { _, _ in false }))
    }
    func testBackupKDF() throws {
        let derived = try XCTUnwrap(BIPService.backupKey("sample-password", salt: Data(repeating: 7, count: 16)))
        XCTAssertEqual(derived.map { String(format: "%02x", $0) }.joined(), "240def6888ca58830aafa31d7bf4b984d5c6ea37016673e2d037d132df945db9")
    }
}
