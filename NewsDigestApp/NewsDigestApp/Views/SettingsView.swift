import SwiftUI

struct SettingsView: View {
    @Environment(DigestStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var urlText = ""

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("https://username.github.io/NewsDigest/digest", text: $urlText)
                        .textFieldStyle(.roundedBorder)
                        .autocorrectionDisabled()
                        #if os(iOS)
                        .textInputAutocapitalization(.never)
                        .keyboardType(.URL)
                        #endif
                } header: {
                    Text("Digest URL")
                } footer: {
                    Text("The folder your pipeline publishes to — the app fetches latest.json, index.json, and dated digests from it. Leave empty to use the bundled sample.")
                }

                Section("About") {
                    Text("NewsDigest gathers articles from major publications once a day, groups coverage of the same event, and lists neutral facts with links to every outlet that reported them, most-corroborated first. Facts link to the original articles; no article text is republished.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Settings")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") {
                        store.baseURLString = urlText
                        dismiss()
                        Task { await store.refresh() }
                    }
                }
            }
        }
        .onAppear { urlText = store.baseURLString }
        #if os(macOS)
        .frame(minWidth: 480, minHeight: 320)
        .padding()
        #endif
    }
}
