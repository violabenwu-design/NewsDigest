import Foundation

// Mirrors pipeline/schema.py (SCHEMA_VERSION 1). JSON is snake_case;
// decoded with .convertFromSnakeCase.

struct Digest: Codable {
    var schemaVersion: Int
    var date: String
    var generatedAt: String
    var sources: [DigestSource]
    var topics: [Topic]
}

struct DigestSource: Codable {
    var outlet: String
    var feeds: [String]
}

struct Topic: Codable, Identifiable, Hashable {
    var id: String
    var title: String
    var articles: [Article]
    var facts: [Fact]
    /// Groups of indexes into `facts`, one group per paragraph (schema v2).
    var paragraphs: [[Int]]?

    var outlets: [String] {
        var seen = Set<String>()
        return articles.map(\.outlet).filter { seen.insert($0).inserted }
    }

    /// Paragraphs resolved to facts, dropping out-of-range indexes.
    var factParagraphs: [[Fact]] {
        guard let paragraphs, !paragraphs.isEmpty else { return [] }
        return paragraphs.map { $0.compactMap { i in facts.indices.contains(i) ? facts[i] : nil } }
            .filter { !$0.isEmpty }
    }
}

struct Article: Codable, Identifiable, Hashable {
    var id: String
    var outlet: String
    var title: String
    var url: String
    var publishedAt: String
}

struct Fact: Codable, Hashable {
    var text: String
    var sources: [String]
}

struct DigestIndex: Codable {
    var dates: [String]
}

extension Digest {
    static func decode(_ data: Data) throws -> Digest {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(Digest.self, from: data)
    }
}
