from datetime import date
from sqlmodel import SQLModel, Session, select
import numpy as np
from db.schema import (
    Publication, Document, DocumentType, 
    Node, NodeType, TagName, SectionType,
    ContentData, EmbeddingSource,
    Relation, RelationType,
    Embedding
)
from db.db import engine, create_db_and_tables

def test_publication():
    """Test creating a publication with valid URLs"""
    publication = Publication(
        title="Test Publication",
        abstract="A test abstract",
        citation="Author et al. (2024)",
        authors="Test Author, Another Author",
        publication_date=date(2024, 1, 1),
        source="Nature",
        source_url="https://www.nature.com/articles/test",
        uri="https://doi.org/10.1038/test"
    )
    return publication

def test_document(publication: Publication):
    """Test creating a document with valid type enum"""
    if publication.id is None:
        raise ValueError("Publication ID is required")
    document = Document(
        publication_id=publication.id,
        type=DocumentType.MAIN,
        download_url="https://www.nature.com/articles/test.pdf",
        description="Main article PDF",
        mime_type="application/pdf",
        charset="utf-8",
        storage_url="s3://bucket/test.pdf",
        file_size=1024,
        language="en",
        version="1.0"
    )
    return document

def test_nodes(document: Document):
    """Test creating nodes with parent-child relationship"""
    # Create positional data
    positional_data = [{
        "page_pdf": 1,
        "page_logical": 1,
        "bbox": {"x1": 0.1, "y1": 0.1, "x2": 0.9, "y2": 0.2}
    }]

    if document.id is None:
        raise ValueError("Document ID is required")
    
    # Create parent section node
    section_node = Node(
        document_id=document.id,
        node_type=NodeType.ELEMENT_NODE,
        tag_name=TagName.SECTION,
        section_type=SectionType.INTRODUCTION,
        sequence_in_parent=1,
        positional_data=positional_data
    )
    
    # Create heading element node
    heading_node = Node(
        document_id=document.id,
        node_type=NodeType.ELEMENT_NODE,
        tag_name=TagName.H1,
        sequence_in_parent=1,
        positional_data=positional_data
    )
    
    # Create text node for heading content
    heading_text_node = Node(
        document_id=document.id,
        node_type=NodeType.TEXT_NODE,
        sequence_in_parent=1,
        positional_data=positional_data
    )
    
    # Create paragraph element node
    paragraph_node = Node(
        document_id=document.id,
        node_type=NodeType.ELEMENT_NODE,
        tag_name=TagName.P,
        sequence_in_parent=2,
        positional_data=positional_data
    )
    
    # Create text node for paragraph content
    paragraph_text_node = Node(
        document_id=document.id,
        node_type=NodeType.TEXT_NODE,
        sequence_in_parent=1,
        positional_data=positional_data
    )
    
    return section_node, heading_node, heading_text_node, paragraph_node, paragraph_text_node

def test_content_data(heading_text_node: Node, paragraph_text_node: Node):
    """Test creating content data for text nodes"""
    if heading_text_node.id is None or paragraph_text_node.id is None:
        raise ValueError("Node ID is required")

    heading_content = ContentData(
        node_id=heading_text_node.id,
        text_content="Introduction",
        embedding_source=EmbeddingSource.TEXT_CONTENT
    )
    
    paragraph_content = ContentData(
        node_id=paragraph_text_node.id,
        text_content="This is a test paragraph with some content for testing purposes.",
        embedding_source=EmbeddingSource.TEXT_CONTENT
    )
    
    return heading_content, paragraph_content

def test_embedding(content_data: ContentData):
    """Test creating an embedding with vector array"""
    if content_data.id is None:
        raise ValueError("ContentData ID is required")

    # Generate random vector and convert to regular Python float list
    vector = np.random.rand(384)
    vector_list = [float(x) for x in vector]  # Convert np.float64 to Python float
    
    embedding = Embedding(
        content_data_id=content_data.id,
        embedding_vector=vector_list,
        model_name="test-embedding-model"
    )
    return embedding

def test_relation(source_node: Node, target_node: Node):
    """Test creating a relation between nodes"""
    if source_node.id is None or target_node.id is None:
        raise ValueError("Node ID is required")

    relation = Relation(
        source_node_id=source_node.id,
        target_node_id=target_node.id,
        relation_type=RelationType.CONTINUES
    )
    return relation

def validate_setup():
    """Run all validation tests"""
    with Session(engine) as session:
        created_objects = []
        try:
            # Test Publication
            publication = test_publication()
            session.add(publication)
            session.commit()
            session.refresh(publication)
            created_objects.append(publication)
            print("✓ Publication created successfully")
            
            # Test Document
            document = test_document(publication)
            session.add(document)
            session.commit()
            session.refresh(document)
            created_objects.append(document)
            print("✓ Document created successfully")
            
            # Test Nodes
            section_node, heading_node, heading_text_node, paragraph_node, paragraph_text_node = test_nodes(document)
            
            # Add nodes to session and commit to get IDs
            session.add(section_node)
            session.commit()
            session.refresh(section_node)
            created_objects.append(section_node)
            
            # Set parent relationships and add remaining nodes
            heading_node.parent_id = section_node.id
            paragraph_node.parent_id = section_node.id
            heading_text_node.parent_id = heading_node.id
            paragraph_text_node.parent_id = paragraph_node.id
            
            session.add(heading_node)
            session.add(paragraph_node)
            session.add(heading_text_node)
            session.add(paragraph_text_node)
            session.commit()
            session.refresh(heading_node)
            session.refresh(paragraph_node)
            session.refresh(heading_text_node)
            session.refresh(paragraph_text_node)
            
            created_objects.extend([heading_node, paragraph_node, heading_text_node, paragraph_text_node])
            print("✓ Nodes created successfully")
            
            # Test parent-child relationships
            loaded_heading = session.exec(
                select(Node).where(Node.id == heading_node.id)
            ).one()
            assert loaded_heading.parent is not None
            assert loaded_heading.parent.id == section_node.id
            print("✓ Parent-child relationship verified")
            
            # Test ContentData
            heading_content, paragraph_content = test_content_data(heading_text_node, paragraph_text_node)
            session.add(heading_content)
            session.add(paragraph_content)
            session.commit()
            session.refresh(heading_content)
            session.refresh(paragraph_content)
            created_objects.extend([heading_content, paragraph_content])
            print("✓ ContentData created successfully")
            
            # Test Embedding
            embedding = test_embedding(paragraph_content)
            session.add(embedding)
            session.commit()
            session.refresh(embedding)
            created_objects.append(embedding)
            print("✓ Embedding created successfully")
            
            # Test vector array retrieval
            loaded_embedding = session.exec(
                select(Embedding).where(Embedding.id == embedding.id)
            ).one()
            assert len(loaded_embedding.embedding_vector) == 384
            print("✓ Embedding vector verified")
            
            # Test Relation
            relation = test_relation(heading_node, paragraph_node)
            session.add(relation)
            session.commit()
            session.refresh(relation)
            created_objects.append(relation)
            print("✓ Relation created successfully")
            
            # Test bidirectional relation relationships
            loaded_relation = session.exec(
                select(Relation).where(Relation.id == relation.id)
            ).one()
            assert loaded_relation.source_node.id == heading_node.id
            assert loaded_relation.target_node.id == paragraph_node.id
            print("✓ Relation relationships verified")
            
            # Test content data relationships
            loaded_content = session.exec(
                select(ContentData).where(ContentData.id == paragraph_content.id)
            ).one()
            assert loaded_content.node.id == paragraph_text_node.id
            print("✓ ContentData relationships verified")
            
            print("\n✓ All validation tests passed successfully!")
            
        except Exception as e:
            print(f"\n❌ Validation failed: {str(e)}")
            raise
        finally:
            # Cleanup test data by properly deleting the objects in reverse order
            for obj in reversed(created_objects):
                session.delete(obj)
            session.commit()
            print("\nTest data properly cleaned up")


if __name__ == "__main__":
    # Set to True to drop all tables and start fresh with a new database
    DROP_ALL = True
    
    if DROP_ALL:
        # Drop all tables
        SQLModel.metadata.drop_all(engine)
    
    # Create all tables
    create_db_and_tables()

    # Validate the setup
    validate_setup()