# A DOM-Based Schema for RAG

## **0. The Approach**

We are going to have an LLM turn the PDF into an HTML document, and then we will programmatically convert the DOM to a graph for storage in (and retrieval from) our database. Our schema will closely follow the data model of the DOM (for ease of ingestion and reconstruction), but we will enrich it with additional fields (provided as `data-` attributes on the DOM nodes in the HTML) and relationships (created from anchor links in the HTML).

As in the DOM, we will have an enum to represent whether the node is an element or a text node. We will capture top-level document structure-- front matter, body matter, and back matter boundaries-- with `header`, `main`, and `footer` tags, respectively. ToC-type sections will be wrapped by `nav` tags. Notes, sidebars, and text boxes will be `aside` elements. We'll make liberal use of `section` tags to represent the document's structure, with `data-section-type` attributes to capture richer semantic labels for the section type.

We'll exclude page headers and footers in our HTML. Each HTML element will have `data-start-page` and (optionally, if the element spans multiple pages) `data-end-page` attributes, which will use PDF page numbers. We'll map PDF page numbers to logical page numbers and use that to enrich the positional data. We'll also map our HTML elements to PDF blocks to get bounding boxes for positional enrichment.

We must limit the tags available to the LLM to those we want to support, e.g., `header`, `main`, `footer`, `figure`, `figcaption`, `table`, `th`, `tr`, `td`, `caption`, `title`, `section`, `nav`, `aside`, `p`, `ul`, `ol`, `li`, `h1`, `h2`, `h3`, `h4`, `h5`, `h6`, `i`, `b`, `u`, `s`, `sup`, `sub`, `a`, `img`, `math`, `code`, `cite`, `blockquote`.

For `TEXT_NODE`s and `img`-typed `ELEMENT_NODE`s, we will have a corresponding record in a content data table that will contain the text content or the image URL, respectively.

## **1. Core Philosophy**

Our design is guided by four key principles:

* **DOM Alignment for Easy Ingestion:** Our schema closely mirrors the HTML DOM structure, making it straightforward to convert parsed HTML into our database representation and vice versa.
* **Unified Node Structure:** Both element nodes and text nodes are represented in a single `NODE` table, with type discrimination via the `node_type` field. This maintains the natural hierarchy of the DOM while keeping the schema simple.
* **Explicit Relationship Modeling:** Beyond the hierarchical parent-child relationships inherent in the DOM, a dedicated `RELATION` table defines semantic connections (the "edges") between nodes, such as footnote references and cross-references.
* **Semantic Enrichment:** We enhance the basic DOM structure with semantic section types and positional data that enable advanced RAG capabilities.
* **Performance:** The unified node structure with proper indexing ensures efficient tree traversal and relationship lookups.

```mermaid
erDiagram
    %% Relationship lines
    PUBLICATION ||--o{ DOCUMENT : has
    DOCUMENT ||--|{ NODE : contains
    NODE ||--o{ NODE : "contains (self-reference)"
    NODE ||--o{ CONTENT_DATA : has
    NODE ||--o{ RELATION : source_of
    NODE ||--o{ RELATION : target_of
    CONTENT_DATA ||--o{ EMBEDDING : has

    %% Entity: PUBLICATION
    PUBLICATION {
        integer id PK "Unique publication identifier"
        string title "Title of the publication"
        text abstract "Optional publication abstract"
        string citation "Formal citation"
        string authors "Author(s) of the publication (comma separated)"
        date publication_date "Date of publication"
        string source "Explicit source repository"
        string source_url "Publication landing page URL"
        string uri "Persistent handle.net URI that redirects to source_url"
    }

    %% ENUM: DocumentType
    DocumentType {
        string MAIN "The main document"
        string SUPPLEMENTAL "A supplemental document"
        string OTHER "Other document type"
    }

    %% ENTITY: DOCUMENT
    DOCUMENT {
        integer id PK "Unique document identifier"
        integer publication_id FK "FK to the PUBLICATION that contains this document"
        DocumentType type "Type of document"
        string download_url "URL to the source document download endpoint"
        string description "Description of the document"
        string mime_type "MIME type of the document"
        string charset "Character set of the document"
        string storage_url "URL to the document storage bucket (s3://...)"
        bigint file_size "Size of the document in bytes"
        string language "Language of the document"
        string version "Version of the document"
    }

    %% ENUM: NodeType
    NodeType {
        string TEXT_NODE
        string ELEMENT_NODE
    }

    %% ENUM: TagName
    TagName {
        string HEADER
        string MAIN
        string FOOTER
        string FIGURE
        string FIGCAPTION
        string TABLE
        string TH
        string TR
        string TD
        string CAPTION
        string TITLE
        string SECTION
        string NAV
        string ASIDE
        string P
        string UL
        string OL
        string LI
        string H1
        string H2
        string H3
        string H4
        string H5
        string H6
        string I
        string B
        string U
        string S
        string SUP
        string SUB
        string A
        string IMG
        string MATH
        string CODE
        string CITE
        string BLOCKQUOTE
    }

    %% ENUM: SectionType
    SectionType {
        string ABSTRACT
        string ACKNOWLEDGEMENTS
        string APPENDIX
        string BIBLIOGRAPHY
        string CHAPTER
        string CONCLUSION
        string COPYRIGHT_PAGE
        string DEDICATION
        string EPILOGUE
        string EXECUTIVE_SUMMARY
        string FOOTER
        string FOREWORD
        string HEADER
        string INDEX
        string INTRODUCTION
        string LIST_OF_BOXES
        string LIST_OF_FIGURES
        string LIST_OF_TABLES
        string NOTES_SECTION
        string PART
        string PREFACE
        string PROLOGUE
        string SECTION
        string STANZA
        string SUBSECTION
        string TABLE_OF_CONTENTS
        string TEXT_BOX
        string TITLE_PAGE
    }

    %% ENUM: EmbeddingSource
    EmbeddingSource {
        string TEXT_CONTENT "Embed the primary text content"
        string DESCRIPTION  "Embed the AI-generated description (for tables, figures)"
        string CAPTION "Embed the original caption (for figures, tables)"
    }

    %% Unified Node Structure
    NODE {
        int id PK
        int document_id FK
        NodeType node_type
        TagName tag_name nullable "The HTML tag name of the node if it is an element node"
        SectionType section_type nullable "The semantic section type of the node if it is a section element"
        int parent_id FK nullable "The ID of the parent node"
        int sequence_in_parent "The sequence number of the node within its parent"
        jsonb positional_data "[{page_pdf: int, page_logical: int, bbox: {x1: float, y1: float, x2: float, y2: float}}, ...]" "JSONB array of positional data for the PDF blocks that make up the node"
    }

    %% Content Data (1:1 with content-bearing nodes)
    CONTENT_DATA {
        int id PK
        int node_id FK
        text text_content nullable
        string storage_url nullable
        string description nullable
        string caption nullable
        EmbeddingSource embedding_source
    }

    %% ENUM: RelationType (for non-hierarchical links)
    RelationType {
        string REFERENCES_NOTE "Text references a footnote or endnote"
        string REFERENCES_CITATION "Text references a bibliographic entry"
        string IS_CAPTIONED_BY "A node is a caption for another node"
        string IS_SUPPLEMENTED_BY "A node is supplemented by another node (e.g., a sidebar or legend)"
        string CONTINUES "A node continues from a previous one (e.g., across sections)"
        string CROSS_REFERENCES "A node references another arbitrary node"
    }

    %% ENTITY: RELATION
    RELATION {
        int id PK "Unique relation identifier"
        int source_node_id FK "The origin node of the relationship"
        int target_node_id FK "The destination node of the relationship"
        RelationType relation_type
    }

    %% ENTITY: EMBEDDING
    EMBEDDING {
        integer id PK "Unique embedding identifier"
        integer content_data_id FK
        vector embedding_vector "Embedding vector"
        string model_name "Name of the embedding model"
        timestamp created_at "Timestamp of when the embedding was created"
    }

    %% ===== CSS STYLING =====
    classDef enumType fill:#ffe6e6,stroke:#ff4757
    classDef mainTable fill:#e6f3ff,stroke:#0066cc

    class DocumentType,NodeType,TagName,SectionType,RelationType,EmbeddingSource enumType
    class PUBLICATION,DOCUMENT,NODE,CONTENT_DATA,RELATION,EMBEDDING mainTable
```

## **3. Key Decisions**

* **DOM-Centric Design:**
    * **HTML Tags as Schema Elements:** We limit the LLM to a controlled vocabulary of HTML tags that map directly to our `TagName` enum. This ensures consistent structure and prevents the generation of unsupported markup.
    * **Unified Node Table:** Both element nodes and text nodes are stored in the same `NODE` table, with the `node_type` field distinguishing between them. This mirrors the DOM structure and simplifies traversal operations.
    * **Content Separation:** Actual content (text, images, descriptions) is stored in a separate `CONTENT_DATA` table, maintaining a clean separation between structure and content.

* **Positional Data and Page Mapping:**
    * **PDF-to-HTML Alignment:** Each HTML element includes `data-start-page` and `data-end-page` attributes using PDF page numbers, which are stored in the `positional_data` JSONB field.
    * **Bounding Box Enrichment:** We map HTML elements to PDF blocks to capture precise bounding boxes for UI highlighting and reference purposes.
    * **Logical Page Number Mapping:** Post-ingestion, we map PDF page numbers to logical page numbers to enrich the positional data for better user experience.
    * **GIN Indexing:** We use GIN indexing on the `positional_data` JSONB field to enable efficient page-based queries.

* **Semantic Enrichment:**
    * **Section Type Annotations:** `section` elements include `data-section-type` attributes that map to our `SectionType` enum, providing rich semantic context beyond basic HTML structure.
    * **Structural Boundaries:** We use semantic HTML5 tags (`header`, `main`, `footer`) to delineate document structure (front matter, body matter, back matter).
    * **Specialized Containers:** `nav` elements wrap table-of-contents sections, `aside` elements contain notes and sidebars, and `figure` elements with `figcaption` provide structured figure representation.

* **Relationship Handling:**
    * **Anchor-Based Relations:** HTML anchor links (`<a>` tags with `href` attributes) are converted to entries in the `RELATION` table, enabling cross-references, footnote links, and citation links.
    * **Deferred Resolution:** During ingestion, we can create relationships with source nodes immediately and resolve target nodes later when the referenced elements are encountered.
    * **Multi-Hop Support:** Complex reference chains (e.g., text → footnote → bibliography entry) are naturally supported through the relationship graph.

* **Content Processing:**
    * **Markdown Preservation:** We preserve formatting elements (`i`, `b`, `u`, `s`, `sup`, `sub`) in the HTML to maintain the original document's visual structure.
    * **Image Handling:** `img` elements store URLs in the `storage_url` field of `CONTENT_DATA`, with optional AI-generated descriptions for embedding purposes.
    * **Math and Code:** Specialized elements (`math`, `code`) are preserved as-is for accurate representation of technical content. 

## **4. Unlocking Advanced RAG Capabilities**

This DOM-based schema enables sophisticated RAG operations:

* **Semantic Node-Based Chunking:** Content is chunked at natural HTML element boundaries (paragraphs, list items, table cells) rather than arbitrary character limits, preserving logical document structure.
* **Multi-Modal Embeddings:** We can selectively embed text content, AI-generated descriptions for tables/figures, or original captions based on the `embedding_source` field, optimizing semantic representation for different content types.
* **Structural Pre-filtering:** Queries can be filtered by HTML tag types (e.g., "search only within `table` elements") or semantic section types (e.g., "search only within `BIBLIOGRAPHY` sections") before vector search, improving both speed and relevance.
* **Hierarchical Context Retrieval:** The parent-child relationships in the node tree allow retrieval of surrounding context (e.g., the section containing a relevant paragraph) or drilling down into sub-components (e.g., individual cells within a relevant table).
* **Cross-Reference Following:** The relationship graph enables intelligent traversal of document connections, such as following footnote references to their sources or exploring citation networks within and across documents.
* **Positional Precision:** Bounding box data enables exact highlighting and reference back to specific locations in the original PDF, enhancing user experience and citation accuracy.

## **5. HTML to Database Schema Mapping**

### PUBLICATION Table
| JSON Path                     | DB Field            | Notes                              
|-------------------------------|---------------------|------------------------------------|
| `id`                          | `id`    | Direct mapping                     |
| `title`                       | `title`             | Direct mapping                     |
| `abstract`                    | `abstract`          | Direct mapping                     |
| `citation`                    | `citation`          | Direct mapping                     |
| `metadata.authors`            | `authors`           | Direct mapping                     |
| `metadata.date`               | `publication_date`  | Direct mapping                     |
| `source`                      | `source`            | Direct mapping                     |
| `source_url`                  | `source_url`        | Direct mapping                     |
| `uri`                         | `uri`               | Direct mapping                     |

### DOCUMENT Table
| JSON Path                     | DB Field            | Notes                              |
|-------------------------------|---------------------|------------------------------------|
| `downloadLinks[*].id`         | `id`       | Direct mapping                     |
| `downloadLinks[*].url`        | `download_url`      | Direct mapping                     |
| `downloadLinks[*].file_info.mime_type` | `mime_type`| Direct mapping                     |
| `downloadLinks[*].file_info.charset`   | `charset`  | Direct mapping                     |
| `downloadLinks[*].type`       | `type`              | Direct mapping                     |
| `downloadLinks[*].text`       | `description`       | Direct mapping                     |
| -                             | `storage_url`       | To be populated during processing  |
| -                             | `file_size`         | To be populated during processing  |

### NODE Table
| HTML Element/Attribute        | DB Field            | Notes                              |
|-------------------------------|---------------------|------------------------------------|
| DOM node type                 | `node_type`         | TEXT_NODE or ELEMENT_NODE          |
| HTML tag name                 | `tag_name`          | Maps to TagName enum               |
| `data-section-type`           | `section_type`      | Maps to SectionType enum           |
| Parent element                | `parent_id`         | FK to parent node                  |
| DOM order                     | `sequence_in_parent`| Child index within parent          |
| `data-start-page`, `data-end-page` | `positional_data`   | PDF page numbers and bounding boxes|

### CONTENT_DATA Table
| HTML Content                  | DB Field            | Notes                              |
|-------------------------------|---------------------|------------------------------------|
| Text node content            | `text_content`      | Direct text content                |
| `img` src attribute           | `storage_url`       | Image file URL                     |
| AI-generated description      | `description`       | For tables, figures, complex content|
| `figcaption`, `caption` text  | `caption`           | Original caption text              |
| Content type                  | `embedding_source`  | Which field to embed               |

### RELATION Table
| HTML Element                  | DB Field            | Notes                              |
|-------------------------------|---------------------|------------------------------------|
| `<a>` source element          | `source_node_id`    | Node containing the link           |
| `href` target                 | `target_node_id`    | Referenced node                    |
| Link purpose/context          | `relation_type`     | Semantic relationship type         |
