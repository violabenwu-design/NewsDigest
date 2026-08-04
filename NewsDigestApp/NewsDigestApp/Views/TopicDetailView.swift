import SwiftUI

struct TopicDetailView: View {
    let topic: Topic

    private var articlesByID: [String: Article] {
        Dictionary(uniqueKeysWithValues: topic.articles.map { ($0.id, $0) })
    }

    var body: some View {
        List {
            let paragraphs = topic.factParagraphs
            if !paragraphs.isEmpty {
                Section {
                    ForEach(Array(paragraphs.enumerated()), id: \.offset) { _, facts in
                        ParagraphView(facts: facts, articlesByID: articlesByID)
                    }
                } header: {
                    Text("The story, fact by fact")
                }
            } else {
                Section {
                    ForEach(topic.facts, id: \.self) { fact in
                        FactRow(fact: fact, articlesByID: articlesByID)
                    }
                } header: {
                    Text("Facts, most corroborated first")
                }
            }

            Section("Coverage") {
                ForEach(topic.articles) { article in
                    if let url = URL(string: article.url) {
                        Link(destination: url) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(article.outlet)
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(.secondary)
                                Text(article.title)
                                    .font(.subheadline)
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .navigationTitle(topic.title)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
    }
}

/// A paragraph of verbatim facts joined in reading order, each sentence
/// followed by small inline links to the article(s) that stated it.
struct ParagraphView: View {
    let facts: [Fact]
    let articlesByID: [String: Article]

    var body: some View {
        Text(attributed)
            .padding(.vertical, 2)
            .tint(.secondary)
    }

    private var attributed: AttributedString {
        var result = AttributedString()
        for (i, fact) in facts.enumerated() {
            result += AttributedString(fact.text)
            let sources = fact.sources.compactMap { articlesByID[$0] }
            if !sources.isEmpty {
                result += AttributedString(" ")
                for (j, article) in sources.enumerated() {
                    var chip = AttributedString(article.outlet)
                    chip.font = .caption2
                    if let url = URL(string: article.url) {
                        chip.link = url
                    }
                    result += chip
                    if j < sources.count - 1 {
                        var sep = AttributedString("·")
                        sep.font = .caption2
                        sep.foregroundColor = .secondary
                        result += sep
                    }
                }
            }
            if i < facts.count - 1 {
                result += AttributedString("  ")
            }
        }
        return result
    }
}

struct FactRow: View {
    let fact: Fact
    let articlesByID: [String: Article]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .top, spacing: 8) {
                Text("\(fact.sources.count)")
                    .font(.caption.weight(.bold))
                    .padding(.horizontal, 7)
                    .padding(.vertical, 3)
                    .background(badgeColor, in: Capsule())
                    .foregroundStyle(.white)
                    .accessibilityLabel("\(fact.sources.count) sources")
                Text(fact.text)
                    .font(.body)
            }
            // one chip per article that stated this fact, linking to the original
            FlowChips(articles: fact.sources.compactMap { articlesByID[$0] })
                .padding(.leading, 30)
        }
        .padding(.vertical, 4)
    }

    private var badgeColor: Color {
        switch fact.sources.count {
        case 3...: .green
        case 2: .blue
        default: .gray
        }
    }
}

struct FlowChips: View {
    let articles: [Article]

    var body: some View {
        // simple wrapping layout for outlet chips
        FlowLayout(spacing: 6) {
            ForEach(articles) { article in
                if let url = URL(string: article.url) {
                    Link(destination: url) {
                        Text(article.outlet)
                            .font(.caption)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(.quaternary, in: Capsule())
                    }
                    .buttonStyle(.plain)
                    .help(article.title)
                }
            }
        }
    }
}

/// Minimal wrapping layout (Layout protocol, iOS 16+/macOS 13+).
struct FlowLayout: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = computeRows(proposal: proposal, subviews: subviews)
        let width = proposal.width ?? rows.map(\.width).max() ?? 0
        let height = rows.reduce(0) { $0 + $1.height } + spacing * CGFloat(max(0, rows.count - 1))
        return CGSize(width: width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for row in computeRows(proposal: proposal, subviews: subviews) {
            var x = bounds.minX
            for index in row.indices {
                let size = subviews[index].sizeThatFits(.unspecified)
                subviews[index].place(at: CGPoint(x: x, y: y), proposal: .unspecified)
                x += size.width + spacing
            }
            y += row.height + spacing
        }
    }

    private struct Row {
        var indices: [Int] = []
        var width: CGFloat = 0
        var height: CGFloat = 0
    }

    private func computeRows(proposal: ProposedViewSize, subviews: Subviews) -> [Row] {
        let maxWidth = proposal.width ?? .infinity
        var rows: [Row] = []
        var current = Row()
        for (index, subview) in subviews.enumerated() {
            let size = subview.sizeThatFits(.unspecified)
            let needed = current.indices.isEmpty ? size.width : current.width + spacing + size.width
            if needed > maxWidth, !current.indices.isEmpty {
                rows.append(current)
                current = Row()
            }
            current.width = current.indices.isEmpty ? size.width : current.width + spacing + size.width
            current.height = max(current.height, size.height)
            current.indices.append(index)
        }
        if !current.indices.isEmpty { rows.append(current) }
        return rows
    }
}
