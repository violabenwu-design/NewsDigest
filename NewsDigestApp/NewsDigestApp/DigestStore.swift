import Foundation
import Observation

@Observable
@MainActor
final class DigestStore {
    var digest: Digest?
    var availableDates: [String] = []
    var isLoading = false
    var lastError: String?
    /// Date currently displayed; nil means "latest".
    var selectedDate: String?

    static let defaultBaseURL = "https://violabenwu-design.github.io/NewsDigest/digest"

    var baseURLString: String {
        get { UserDefaults.standard.string(forKey: "digestBaseURL") ?? Self.defaultBaseURL }
        set {
            UserDefaults.standard.set(newValue, forKey: "digestBaseURL")
        }
    }

    private var cacheURL: URL {
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("NewsDigest", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("cached-digest.json")
    }

    init() {
        loadCachedOrSample()
    }

    /// On launch: last successfully fetched digest, else the bundled sample.
    private func loadCachedOrSample() {
        if let data = try? Data(contentsOf: cacheURL), let cached = try? Digest.decode(data) {
            digest = cached
            return
        }
        if let url = Bundle.main.url(forResource: "SampleDigest", withExtension: "json"),
           let data = try? Data(contentsOf: url) {
            digest = try? Digest.decode(data)
        }
    }

    private func digestURL(for date: String?) -> URL? {
        let base = baseURLString.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !base.isEmpty, var url = URL(string: base) else { return nil }
        url.append(path: date.map { "\($0).json" } ?? "latest.json")
        return url
    }

    func refresh() async {
        await load(date: selectedDate)
        await refreshIndex()
    }

    func select(date: String?) async {
        selectedDate = date
        await load(date: date)
    }

    private func load(date: String?) async {
        guard let url = digestURL(for: date) else {
            lastError = baseURLString.isEmpty
                ? "No digest URL configured — showing sample data. Set your GitHub Pages URL in Settings."
                : "The digest URL in Settings is not a valid URL."
            return
        }
        isLoading = true
        defer { isLoading = false }
        do {
            let (data, response) = try await URLSession.shared.data(from: url)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                throw URLError(.badServerResponse)
            }
            let fetched = try Digest.decode(data)
            digest = fetched
            lastError = nil
            if date == nil {
                try? data.write(to: cacheURL)
            }
        } catch {
            lastError = "Couldn't load the digest (\(error.localizedDescription)). Showing the last saved copy."
        }
    }

    private func refreshIndex() async {
        let base = baseURLString.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !base.isEmpty, var url = URL(string: base) else { return }
        url.append(path: "index.json")
        if let (data, _) = try? await URLSession.shared.data(from: url),
           let index = try? JSONDecoder().decode(DigestIndex.self, from: data) {
            availableDates = index.dates.sorted(by: >)
        }
    }
}
