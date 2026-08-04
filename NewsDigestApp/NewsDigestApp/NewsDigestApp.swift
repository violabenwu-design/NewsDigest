import SwiftUI

@main
struct NewsDigestApp: App {
    @State private var store = DigestStore()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(store)
                .task { await store.refresh() }
        }
        #if os(macOS)
        .defaultSize(width: 1000, height: 700)
        #endif
    }
}

struct ContentView: View {
    @Environment(DigestStore.self) private var store
    @State private var selectedTopic: Topic?
    @State private var showingSettings = false

    var body: some View {
        NavigationSplitView {
            TopicListView(selection: $selectedTopic)
                .navigationTitle(titleText)
                .toolbar {
                    ToolbarItem {
                        archiveMenu
                    }
                    ToolbarItem {
                        Button {
                            showingSettings = true
                        } label: {
                            Label("Settings", systemImage: "gearshape")
                        }
                    }
                    ToolbarItem {
                        if store.isLoading {
                            ProgressView()
                        } else {
                            Button {
                                Task { await store.refresh() }
                            } label: {
                                Label("Refresh", systemImage: "arrow.clockwise")
                            }
                        }
                    }
                }
        } detail: {
            if let topic = selectedTopic {
                TopicDetailView(topic: topic)
            } else {
                ContentUnavailableView(
                    "Select a Topic",
                    systemImage: "newspaper",
                    description: Text("Pick a story to see its corroborated facts.")
                )
            }
        }
        .sheet(isPresented: $showingSettings) {
            SettingsView()
        }
    }

    private var titleText: String {
        if let date = store.digest?.date {
            return "Digest \(date)"
        }
        return "NewsDigest"
    }

    private var archiveMenu: some View {
        Menu {
            Button("Latest") {
                Task { await store.select(date: nil) }
            }
            ForEach(store.availableDates, id: \.self) { date in
                Button(date) {
                    Task { await store.select(date: date) }
                }
            }
        } label: {
            Label("Archive", systemImage: "calendar")
        }
    }
}
