import SwiftUI

struct TopicListView: View {
    @Environment(DigestStore.self) private var store
    @Binding var selection: Topic?

    var body: some View {
        Group {
            if let digest = store.digest, !digest.topics.isEmpty {
                List(digest.topics, selection: $selection) { topic in
                    NavigationLink(value: topic) {
                        TopicRow(topic: topic)
                    }
                }
                .refreshable { await store.refresh() }
            } else {
                ContentUnavailableView(
                    "No Digest Yet",
                    systemImage: "newspaper",
                    description: Text(store.lastError ?? "Pull to refresh once the pipeline has published a digest.")
                )
            }
        }
        .overlay(alignment: .bottom) {
            if let error = store.lastError, store.digest != nil {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(8)
                    .frame(maxWidth: .infinity)
                    .background(.thinMaterial)
            }
        }
    }
}

struct TopicRow: View {
    let topic: Topic

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(topic.title)
                .font(.headline)
                .lineLimit(3)
            Text(topic.outlets.joined(separator: " · "))
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(2)
            if let top = topic.facts.first {
                Text(top.text)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 4)
    }
}
