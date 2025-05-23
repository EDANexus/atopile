# Atopile Parser

This directory contains the ANTLR grammar files (`.g4`), the generated Python parser code, and utilities related to parsing `.ato` files.

## `front_end.py` Workflow

The `front_end.py` module is responsible for taking the Abstract Syntax Tree (AST) generated by the parser and constructing the corresponding Faebryk object graph. It uses two main visitor classes: `Wendy` for initial surveying and `Bob` for building the graph.

```mermaid
graph TD
    subgraph Entrypoints
        direction LR
        E1[build_file] --> E_Prep
        E2[build_ast] --> E_Prep
    end

    subgraph Initialization
        direction TB
        E_Prep[Sanitize Path / Get Context] --> B_Build[_build]
    end

    subgraph Indexing [Wendy]
        direction TB
        B_Build --> I_Index{Index AST/File?}
        I_Index -- Yes --> I_Cache[Return Cached Context]
        I_Index -- No --> I_Survey[Wendy.survey]
        I_Survey --> I_Visit[Wendy.visitFile_input / visitBlockdef]
        I_Visit --> I_VisitStmt[Wendy.visitSimple_stmt]
        I_VisitStmt --> I_VisitImport[Wendy.visitImport_stmt / visitDep_import_stmt]
        I_VisitStmt --> I_VisitBlockDef[Wendy.visitBlockdef]
        I_VisitImport --> I_PopulateCtx[Populate Context Refs w/ ImportPlaceholders]
        I_VisitBlockDef --> I_PopulateCtx[Populate Context Refs w/ BlockdefContext]
        I_PopulateCtx --> I_CheckShim{Shim Available?}
        I_CheckShim -- Yes --> I_AddShim[Add Shim Class to Context Refs]
        I_CheckShim -- No --> I_StoreCtx[Store Context in Cache]
        I_AddShim --> I_StoreCtx
        I_StoreCtx --> I_Cache
        I_Cache --> B_Build
    end

    subgraph Building [Bob]
        direction TB
        B_Build --> B_GetRefClass[_get_referenced_class]
        B_GetRefClass --> B_FindScope{Find Scope Context?}
        B_FindScope -- Yes --> B_CheckRefInCtx{Ref in Context Refs?}
        B_FindScope -- No --> B_Error1[Error: Scope Not Found]
        B_CheckRefInCtx -- No --> B_Error2[Error: Ref Not Found]
        B_CheckRefInCtx -- Yes --> B_CheckImport{ImportPlaceholder?}
        B_CheckImport -- Yes --> B_ImportItem[_import_item]
        B_ImportItem --> B_FindImportPath{Find Import File?}
        B_FindImportPath -- No --> B_Error3[Error: Import Not Found]
        B_FindImportPath -- Yes --> B_ParseImport{Parse .py / .ato File}
        B_ParseImport --> B_GetImportedItem[Get Class/BlockDef]
        B_GetImportedItem --> B_UpdateCtx[Update Context Ref]
        B_CheckImport -- No --> B_ReturnClass[Return Class / BlockDef Context]
        B_UpdateCtx --> B_ReturnClass
        B_ReturnClass --> B_InitNode[_init_node contextmanager]

        B_InitNode --> B_NewNode[_new_node]
        B_NewNode --> B_NewNodeRecurse{Base Class?}
        B_NewNodeRecurse -- No --> B_GetSuperClass[Get Superclass Ref]
        B_GetSuperClass --> B_GetRefClass
        B_GetSuperClass --> B_RecurseNewNode[Recurse _new_node w/ promised_super]
        B_RecurseNewNode --> B_NewNode
        B_NewNodeRecurse -- Yes --> B_CreatePyClass{Create Python Classes for Supers?}
        B_CreatePyClass -- Yes --> B_CachePyClass[Cache Python Class]
        B_CreatePyClass -- No --> B_Instantiate[Instantiate Node]
        B_CachePyClass --> B_Instantiate
        B_Instantiate --> B_ReturnHollowNode[Return Hollow Node & Promised Supers]
        B_ReturnHollowNode --> B_YieldNode[Yield Hollow Node]

        B_YieldNode --> B_AddNodeToGraph["Add Node to Parent (visitAssign_stmt)"]
        B_AddNodeToGraph --> B_PostYield[Post-Yield Processing]
        B_PostYield --> B_PushStacks[Push Node & Traceback Stacks]
        B_PushStacks --> B_VisitSupers{Visit Promised Supers?}
        B_VisitSupers -- Yes --> B_VisitSuperBlock[Bob.visitBlock]
        B_VisitSupers -- No --> B_InitDone[Node Init Done]
        B_VisitSuperBlock --> B_VisitStmts[Bob.visit Statements]

        subgraph Statement Processing
            direction TB
            B_VisitStmts --> B_VisitAssign[visitAssign_stmt]
            B_VisitStmts --> B_VisitConnect[visitConnect_stmt]
            B_VisitStmts --> B_VisitRetype[visitRetype_stmt]
            B_VisitStmts --> B_VisitPinSig[visitPindef/Signaldef_stmt]
            B_VisitStmts --> B_VisitDeclare[visitDeclaration_stmt]
            B_VisitStmts --> B_VisitAssert[visitAssert_stmt]
            B_VisitStmts --> B_VisitCumAssign[visitCum_assign_stmt / visitSet_assign_stmt]
            B_VisitStmts --> B_OtherVisits[...]

            B_VisitAssign --> B_AssignNew{new Keyword?}
            B_AssignNew -- Yes --> B_GetRefClass --> B_InitNode
            B_AssignNew -- No --> B_AssignValue[Visit Assignable Value]
            B_AssignValue --> B_AssignParam{Parameter?}
            B_AssignParam -- Yes --> B_EnsureParam[_ensure_param]
            B_EnsureParam --> B_RecordParamAssign[Record Parameter Assignment]
            B_AssignParam -- No --> B_AssignAttr{String/Bool?}
            B_AssignAttr -- Yes --> B_SetAttr[setattr / GlobalAttributes Shim]
            B_RecordParamAssign --> B_StmtDone[Statement Done]
            B_SetAttr --> B_StmtDone
            B_AssignAttr -- No --> B_Error4[Error: Unhandled Assignable]

            B_VisitConnect --> B_VisitConnectable[Visit Connectables]
            B_VisitConnectable --> B_GetRefNode[_get_referenced_node]
            B_GetRefNode --> B_Connect[_connect]
            B_Connect --> B_ConnectAttempt{Connect OK?}
            B_ConnectAttempt -- No --> B_ConnectDuck{Duck-Type Connect OK?}
            B_ConnectAttempt -- Yes --> B_StmtDone
            B_ConnectDuck -- Yes --> B_WarnDuck[Warn Deprecated] --> B_StmtDone
            B_ConnectDuck -- No --> B_Error5[Error: Connection Failed]

            B_VisitRetype --> B_GetFromNode[_get_referenced_node]
            B_GetFromNode --> B_GetToClass[_get_referenced_class]
            B_GetToClass --> B_InitNode --> B_SpecializedNode[Create Specialized Node]
            B_SpecializedNode --> B_ReplaceNode[Replace Original Node in Graph]
            B_ReplaceNode --> B_Specialize[from_node.specialize]
            B_Specialize --> B_SpecializeOk{Specialization OK?}
            B_SpecializeOk -- Yes --> B_StmtDone
            B_SpecializeOk -- No --> B_Error6[Error: Invalid Specialization]

            B_VisitPinSig --> B_AddPinSig[Add Pin/Signal MIF] --> B_StmtDone
            B_VisitDeclare --> B_HandleParamDecl[_handleParameterDeclaration]
            B_HandleParamDecl --> B_EnsureParam
            B_HandleParamDecl --> B_RecordParamDecl[Record Parameter Declaration] --> B_StmtDone

            B_VisitAssert --> B_VisitComparison[visitComparison]
            B_VisitComparison --> B_VisitArithExpr[visitArithmetic_expression etc.]
            B_VisitArithExpr --> B_BuildExpr[Build Faebryk Expression]
            B_BuildExpr --> B_AssertExpr{Assert Expression OK?}
            B_AssertExpr -- Yes --> B_StmtDone
            B_AssertExpr -- No --> B_Error7[Error: Assertion Failed]

            B_VisitCumAssign --> B_GetParam[_get_param]
            B_GetParam --> B_VisitCumAssignable[Visit Assignable]
            B_VisitCumAssignable --> B_ConstrainAlias[Assignee.constrain/alias] --> B_StmtDone
        end

        B_StmtDone --> B_PopStacks[Pop Node & Traceback Stacks]
        B_PopStacks --> B_InitDone
        B_InitDone --> B_ReturnNode[Return Built Node]
    end


    subgraph Finalization
        direction TB
        B_ReturnNode --> F_Finish[_finish]
        F_Finish --> F_MergeParams[_merge_parameter_assignments]
        F_MergeParams --> F_ProcessParams{Process Recorded Params}
        F_ProcessParams --> F_ApplyConstraints[Apply Constraints/Aliases]
        F_ApplyConstraints --> F_Done[Done]
    end

    subgraph Error Handling
        style Error Handling fill:#f9f,stroke:#333,stroke-width:2px
        B_Error1 --> EH_Handle[Handle Error]
        B_Error2 --> EH_Handle
        B_Error3 --> EH_Handle
        B_Error4 --> EH_Handle
        B_Error5 --> EH_Handle
        B_Error6 --> EH_Handle
        B_Error7 --> EH_Handle
        EH_Handle --> F_Done
    end
```

## Installing ANTLR

1. Make sure you're running native brew (an issue if you're on OSx with Rosetta - because you mightn't notice)
2. Install java
3. `pip install antlr4-tools`

I thiiiiink that should work, but it was a bit of a PITA and there's a chance I missed something.

## Building this

cd to the `src/atopile/parser` directory and run the following command:

`antlr4 -visitor -no-listener -Dlanguage=Python3 AtoLexer.g4 AtoParser.g4`

