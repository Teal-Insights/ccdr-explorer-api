#!/usr/bin/env python3
"""
Script to delete ContentData and Embedding records associated with a specific document.
The Publication and Document records remain intact.
"""

import argparse
import sys
from sqlmodel import Session, select, delete
from db.db import engine
from db.schema import ContentData, Embedding, Node


def delete_document_content(document_id: int) -> tuple[int, int]:
    """
    Delete all ContentData and Embedding records associated with a document.
    
    Returns:
        Tuple of (content_data_count, embedding_count) deleted
    """
    with Session(engine) as session:
        # First, get all ContentData records associated with this document
        # We need to join through Node to get to the document_id
        content_data_query = (
            select(ContentData)
            .join(Node)
            .where(Node.document_id == document_id)
        )
        content_data_records = session.exec(content_data_query).all()
        
        content_data_count = len(content_data_records)
        embedding_count = 0
        
        # For each ContentData record, delete associated Embeddings first
        for content_data in content_data_records:
            # Count embeddings before deletion
            embeddings_query = select(Embedding).where(Embedding.content_data_id == content_data.id)
            embeddings = session.exec(embeddings_query).all()
            embedding_count += len(embeddings)
            
            # Delete embeddings
            delete_stmt = delete(Embedding).where(Embedding.content_data_id == content_data.id)
            session.exec(delete_stmt)
        
        # Now delete all ContentData records
        # We can't use a simple join in the delete statement with SQLModel,
        # so we delete by IDs
        content_data_ids = [cd.id for cd in content_data_records]
        if content_data_ids:
            delete_stmt = delete(ContentData).where(ContentData.id.in_(content_data_ids))
            session.exec(delete_stmt)
        
        # Commit the transaction
        session.commit()
        
        return content_data_count, embedding_count


def main():
    parser = argparse.ArgumentParser(
        description="Delete ContentData and Embedding records for a specific document"
    )
    parser.add_argument(
        "document_id",
        type=int,
        help="The ID of the document whose content should be deleted"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Skip confirmation prompt"
    )
    
    args = parser.parse_args()
    
    # Confirmation prompt unless --confirm is passed
    if not args.confirm:
        response = input(f"Are you sure you want to delete all content data and embeddings for document {args.document_id}? (yes/no): ")
        if response.lower() != "yes":
            print("Deletion cancelled.")
            sys.exit(0)
    
    try:
        print(f"Deleting content for document {args.document_id}...")
        content_count, embedding_count = delete_document_content(args.document_id)
        print(f"Successfully deleted {content_count} ContentData records and {embedding_count} Embedding records.")
    except Exception as e:
        print(f"Error during deletion: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()