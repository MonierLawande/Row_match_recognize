# Generated from TrinoParser.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .TrinoParser import TrinoParser
else:
    from TrinoParser import TrinoParser

# This class defines a complete generic visitor for a parse tree produced by TrinoParser.

class TrinoParserVisitor(ParseTreeVisitor):

    # Visit a parse tree produced by TrinoParser#parse.
    def visitParse(self, ctx:TrinoParser.ParseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#statements.
    def visitStatements(self, ctx:TrinoParser.StatementsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#singleStatement.
    def visitSingleStatement(self, ctx:TrinoParser.SingleStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#standaloneExpression.
    def visitStandaloneExpression(self, ctx:TrinoParser.StandaloneExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#standalonePathSpecification.
    def visitStandalonePathSpecification(self, ctx:TrinoParser.StandalonePathSpecificationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#standaloneType.
    def visitStandaloneType(self, ctx:TrinoParser.StandaloneTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#standaloneRowPattern.
    def visitStandaloneRowPattern(self, ctx:TrinoParser.StandaloneRowPatternContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#standaloneFunctionSpecification.
    def visitStandaloneFunctionSpecification(self, ctx:TrinoParser.StandaloneFunctionSpecificationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#statementDefault.
    def visitStatementDefault(self, ctx:TrinoParser.StatementDefaultContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#use.
    def visitUse(self, ctx:TrinoParser.UseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#createCatalog.
    def visitCreateCatalog(self, ctx:TrinoParser.CreateCatalogContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#dropCatalog.
    def visitDropCatalog(self, ctx:TrinoParser.DropCatalogContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#createSchema.
    def visitCreateSchema(self, ctx:TrinoParser.CreateSchemaContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#dropSchema.
    def visitDropSchema(self, ctx:TrinoParser.DropSchemaContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#renameSchema.
    def visitRenameSchema(self, ctx:TrinoParser.RenameSchemaContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#setSchemaAuthorization.
    def visitSetSchemaAuthorization(self, ctx:TrinoParser.SetSchemaAuthorizationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#createTableAsSelect.
    def visitCreateTableAsSelect(self, ctx:TrinoParser.CreateTableAsSelectContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#createTable.
    def visitCreateTable(self, ctx:TrinoParser.CreateTableContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#dropTable.
    def visitDropTable(self, ctx:TrinoParser.DropTableContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#insertInto.
    def visitInsertInto(self, ctx:TrinoParser.InsertIntoContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#delete.
    def visitDelete(self, ctx:TrinoParser.DeleteContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#truncateTable.
    def visitTruncateTable(self, ctx:TrinoParser.TruncateTableContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#commentTable.
    def visitCommentTable(self, ctx:TrinoParser.CommentTableContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#commentView.
    def visitCommentView(self, ctx:TrinoParser.CommentViewContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#commentColumn.
    def visitCommentColumn(self, ctx:TrinoParser.CommentColumnContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#renameTable.
    def visitRenameTable(self, ctx:TrinoParser.RenameTableContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#addColumn.
    def visitAddColumn(self, ctx:TrinoParser.AddColumnContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#renameColumn.
    def visitRenameColumn(self, ctx:TrinoParser.RenameColumnContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#dropColumn.
    def visitDropColumn(self, ctx:TrinoParser.DropColumnContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#setColumnType.
    def visitSetColumnType(self, ctx:TrinoParser.SetColumnTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#setTableAuthorization.
    def visitSetTableAuthorization(self, ctx:TrinoParser.SetTableAuthorizationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#setTableProperties.
    def visitSetTableProperties(self, ctx:TrinoParser.SetTablePropertiesContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#tableExecute.
    def visitTableExecute(self, ctx:TrinoParser.TableExecuteContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#analyze.
    def visitAnalyze(self, ctx:TrinoParser.AnalyzeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#createMaterializedView.
    def visitCreateMaterializedView(self, ctx:TrinoParser.CreateMaterializedViewContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#createView.
    def visitCreateView(self, ctx:TrinoParser.CreateViewContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#refreshMaterializedView.
    def visitRefreshMaterializedView(self, ctx:TrinoParser.RefreshMaterializedViewContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#dropMaterializedView.
    def visitDropMaterializedView(self, ctx:TrinoParser.DropMaterializedViewContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#renameMaterializedView.
    def visitRenameMaterializedView(self, ctx:TrinoParser.RenameMaterializedViewContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#setMaterializedViewProperties.
    def visitSetMaterializedViewProperties(self, ctx:TrinoParser.SetMaterializedViewPropertiesContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#dropView.
    def visitDropView(self, ctx:TrinoParser.DropViewContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#renameView.
    def visitRenameView(self, ctx:TrinoParser.RenameViewContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#setViewAuthorization.
    def visitSetViewAuthorization(self, ctx:TrinoParser.SetViewAuthorizationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#call.
    def visitCall(self, ctx:TrinoParser.CallContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#createFunction.
    def visitCreateFunction(self, ctx:TrinoParser.CreateFunctionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#dropFunction.
    def visitDropFunction(self, ctx:TrinoParser.DropFunctionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#createRole.
    def visitCreateRole(self, ctx:TrinoParser.CreateRoleContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#dropRole.
    def visitDropRole(self, ctx:TrinoParser.DropRoleContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#grantRoles.
    def visitGrantRoles(self, ctx:TrinoParser.GrantRolesContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#revokeRoles.
    def visitRevokeRoles(self, ctx:TrinoParser.RevokeRolesContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#setRole.
    def visitSetRole(self, ctx:TrinoParser.SetRoleContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#grant.
    def visitGrant(self, ctx:TrinoParser.GrantContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#deny.
    def visitDeny(self, ctx:TrinoParser.DenyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#revoke.
    def visitRevoke(self, ctx:TrinoParser.RevokeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#showGrants.
    def visitShowGrants(self, ctx:TrinoParser.ShowGrantsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#explain.
    def visitExplain(self, ctx:TrinoParser.ExplainContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#explainAnalyze.
    def visitExplainAnalyze(self, ctx:TrinoParser.ExplainAnalyzeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#showCreateTable.
    def visitShowCreateTable(self, ctx:TrinoParser.ShowCreateTableContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#showCreateSchema.
    def visitShowCreateSchema(self, ctx:TrinoParser.ShowCreateSchemaContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#showCreateView.
    def visitShowCreateView(self, ctx:TrinoParser.ShowCreateViewContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#showCreateMaterializedView.
    def visitShowCreateMaterializedView(self, ctx:TrinoParser.ShowCreateMaterializedViewContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#showTables.
    def visitShowTables(self, ctx:TrinoParser.ShowTablesContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#showSchemas.
    def visitShowSchemas(self, ctx:TrinoParser.ShowSchemasContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#showCatalogs.
    def visitShowCatalogs(self, ctx:TrinoParser.ShowCatalogsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#showColumns.
    def visitShowColumns(self, ctx:TrinoParser.ShowColumnsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#showStats.
    def visitShowStats(self, ctx:TrinoParser.ShowStatsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#showStatsForQuery.
    def visitShowStatsForQuery(self, ctx:TrinoParser.ShowStatsForQueryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#showRoles.
    def visitShowRoles(self, ctx:TrinoParser.ShowRolesContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#showRoleGrants.
    def visitShowRoleGrants(self, ctx:TrinoParser.ShowRoleGrantsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#showFunctions.
    def visitShowFunctions(self, ctx:TrinoParser.ShowFunctionsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#showSession.
    def visitShowSession(self, ctx:TrinoParser.ShowSessionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#setSessionAuthorization.
    def visitSetSessionAuthorization(self, ctx:TrinoParser.SetSessionAuthorizationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#resetSessionAuthorization.
    def visitResetSessionAuthorization(self, ctx:TrinoParser.ResetSessionAuthorizationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#setSession.
    def visitSetSession(self, ctx:TrinoParser.SetSessionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#resetSession.
    def visitResetSession(self, ctx:TrinoParser.ResetSessionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#startTransaction.
    def visitStartTransaction(self, ctx:TrinoParser.StartTransactionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#commit.
    def visitCommit(self, ctx:TrinoParser.CommitContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#rollback.
    def visitRollback(self, ctx:TrinoParser.RollbackContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#prepare.
    def visitPrepare(self, ctx:TrinoParser.PrepareContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#deallocate.
    def visitDeallocate(self, ctx:TrinoParser.DeallocateContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#execute.
    def visitExecute(self, ctx:TrinoParser.ExecuteContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#executeImmediate.
    def visitExecuteImmediate(self, ctx:TrinoParser.ExecuteImmediateContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#describeInput.
    def visitDescribeInput(self, ctx:TrinoParser.DescribeInputContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#describeOutput.
    def visitDescribeOutput(self, ctx:TrinoParser.DescribeOutputContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#setPath.
    def visitSetPath(self, ctx:TrinoParser.SetPathContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#setTimeZone.
    def visitSetTimeZone(self, ctx:TrinoParser.SetTimeZoneContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#update.
    def visitUpdate(self, ctx:TrinoParser.UpdateContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#merge.
    def visitMerge(self, ctx:TrinoParser.MergeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#rootQuery.
    def visitRootQuery(self, ctx:TrinoParser.RootQueryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#withFunction.
    def visitWithFunction(self, ctx:TrinoParser.WithFunctionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#query.
    def visitQuery(self, ctx:TrinoParser.QueryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#with.
    def visitWith(self, ctx:TrinoParser.WithContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#tableElement.
    def visitTableElement(self, ctx:TrinoParser.TableElementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#columnDefinition.
    def visitColumnDefinition(self, ctx:TrinoParser.ColumnDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#likeClause.
    def visitLikeClause(self, ctx:TrinoParser.LikeClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#properties.
    def visitProperties(self, ctx:TrinoParser.PropertiesContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#propertyAssignments.
    def visitPropertyAssignments(self, ctx:TrinoParser.PropertyAssignmentsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#property.
    def visitProperty(self, ctx:TrinoParser.PropertyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#defaultPropertyValue.
    def visitDefaultPropertyValue(self, ctx:TrinoParser.DefaultPropertyValueContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#nonDefaultPropertyValue.
    def visitNonDefaultPropertyValue(self, ctx:TrinoParser.NonDefaultPropertyValueContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#queryNoWith.
    def visitQueryNoWith(self, ctx:TrinoParser.QueryNoWithContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#limitRowCount.
    def visitLimitRowCount(self, ctx:TrinoParser.LimitRowCountContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#rowCount.
    def visitRowCount(self, ctx:TrinoParser.RowCountContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#queryTermDefault.
    def visitQueryTermDefault(self, ctx:TrinoParser.QueryTermDefaultContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#setOperation.
    def visitSetOperation(self, ctx:TrinoParser.SetOperationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#queryPrimaryDefault.
    def visitQueryPrimaryDefault(self, ctx:TrinoParser.QueryPrimaryDefaultContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#table.
    def visitTable(self, ctx:TrinoParser.TableContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#inlineTable.
    def visitInlineTable(self, ctx:TrinoParser.InlineTableContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#subquery.
    def visitSubquery(self, ctx:TrinoParser.SubqueryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#sortItem.
    def visitSortItem(self, ctx:TrinoParser.SortItemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#querySpecification.
    def visitQuerySpecification(self, ctx:TrinoParser.QuerySpecificationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#groupBy.
    def visitGroupBy(self, ctx:TrinoParser.GroupByContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#singleGroupingSet.
    def visitSingleGroupingSet(self, ctx:TrinoParser.SingleGroupingSetContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#rollup.
    def visitRollup(self, ctx:TrinoParser.RollupContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#cube.
    def visitCube(self, ctx:TrinoParser.CubeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#multipleGroupingSets.
    def visitMultipleGroupingSets(self, ctx:TrinoParser.MultipleGroupingSetsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#groupingSet.
    def visitGroupingSet(self, ctx:TrinoParser.GroupingSetContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#windowDefinition.
    def visitWindowDefinition(self, ctx:TrinoParser.WindowDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#windowSpecification.
    def visitWindowSpecification(self, ctx:TrinoParser.WindowSpecificationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#namedQuery.
    def visitNamedQuery(self, ctx:TrinoParser.NamedQueryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#setQuantifier.
    def visitSetQuantifier(self, ctx:TrinoParser.SetQuantifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#selectSingle.
    def visitSelectSingle(self, ctx:TrinoParser.SelectSingleContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#selectAll.
    def visitSelectAll(self, ctx:TrinoParser.SelectAllContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#relationDefault.
    def visitRelationDefault(self, ctx:TrinoParser.RelationDefaultContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#joinRelation.
    def visitJoinRelation(self, ctx:TrinoParser.JoinRelationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#joinType.
    def visitJoinType(self, ctx:TrinoParser.JoinTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#joinCriteria.
    def visitJoinCriteria(self, ctx:TrinoParser.JoinCriteriaContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#sampledRelation.
    def visitSampledRelation(self, ctx:TrinoParser.SampledRelationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#sampleType.
    def visitSampleType(self, ctx:TrinoParser.SampleTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#trimsSpecification.
    def visitTrimsSpecification(self, ctx:TrinoParser.TrimsSpecificationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#listAggOverflowBehavior.
    def visitListAggOverflowBehavior(self, ctx:TrinoParser.ListAggOverflowBehaviorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#listaggCountIndication.
    def visitListaggCountIndication(self, ctx:TrinoParser.ListaggCountIndicationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#patternRecognition.
    def visitPatternRecognition(self, ctx:TrinoParser.PatternRecognitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#measureDefinition.
    def visitMeasureDefinition(self, ctx:TrinoParser.MeasureDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#rowsPerMatch.
    def visitRowsPerMatch(self, ctx:TrinoParser.RowsPerMatchContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#emptyMatchHandling.
    def visitEmptyMatchHandling(self, ctx:TrinoParser.EmptyMatchHandlingContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#skipTo.
    def visitSkipTo(self, ctx:TrinoParser.SkipToContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#subsetDefinition.
    def visitSubsetDefinition(self, ctx:TrinoParser.SubsetDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#variableDefinition.
    def visitVariableDefinition(self, ctx:TrinoParser.VariableDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#aliasedRelation.
    def visitAliasedRelation(self, ctx:TrinoParser.AliasedRelationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#columnAliases.
    def visitColumnAliases(self, ctx:TrinoParser.ColumnAliasesContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#tableName.
    def visitTableName(self, ctx:TrinoParser.TableNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#subqueryRelation.
    def visitSubqueryRelation(self, ctx:TrinoParser.SubqueryRelationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#unnest.
    def visitUnnest(self, ctx:TrinoParser.UnnestContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#lateral.
    def visitLateral(self, ctx:TrinoParser.LateralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#tableFunctionInvocation.
    def visitTableFunctionInvocation(self, ctx:TrinoParser.TableFunctionInvocationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#parenthesizedRelation.
    def visitParenthesizedRelation(self, ctx:TrinoParser.ParenthesizedRelationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#tableFunctionCall.
    def visitTableFunctionCall(self, ctx:TrinoParser.TableFunctionCallContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#tableFunctionArgument.
    def visitTableFunctionArgument(self, ctx:TrinoParser.TableFunctionArgumentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#tableArgument.
    def visitTableArgument(self, ctx:TrinoParser.TableArgumentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#tableArgumentTable.
    def visitTableArgumentTable(self, ctx:TrinoParser.TableArgumentTableContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#tableArgumentQuery.
    def visitTableArgumentQuery(self, ctx:TrinoParser.TableArgumentQueryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#descriptorArgument.
    def visitDescriptorArgument(self, ctx:TrinoParser.DescriptorArgumentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#descriptorField.
    def visitDescriptorField(self, ctx:TrinoParser.DescriptorFieldContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#copartitionTables.
    def visitCopartitionTables(self, ctx:TrinoParser.CopartitionTablesContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#expression.
    def visitExpression(self, ctx:TrinoParser.ExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#logicalNot.
    def visitLogicalNot(self, ctx:TrinoParser.LogicalNotContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#predicated.
    def visitPredicated(self, ctx:TrinoParser.PredicatedContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#or.
    def visitOr(self, ctx:TrinoParser.OrContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#and.
    def visitAnd(self, ctx:TrinoParser.AndContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#comparison.
    def visitComparison(self, ctx:TrinoParser.ComparisonContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#quantifiedComparison.
    def visitQuantifiedComparison(self, ctx:TrinoParser.QuantifiedComparisonContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#between.
    def visitBetween(self, ctx:TrinoParser.BetweenContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#inList.
    def visitInList(self, ctx:TrinoParser.InListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#inSubquery.
    def visitInSubquery(self, ctx:TrinoParser.InSubqueryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#like.
    def visitLike(self, ctx:TrinoParser.LikeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#nullPredicate.
    def visitNullPredicate(self, ctx:TrinoParser.NullPredicateContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#distinctFrom.
    def visitDistinctFrom(self, ctx:TrinoParser.DistinctFromContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#valueExpressionDefault.
    def visitValueExpressionDefault(self, ctx:TrinoParser.ValueExpressionDefaultContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#concatenation.
    def visitConcatenation(self, ctx:TrinoParser.ConcatenationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#arithmeticBinary.
    def visitArithmeticBinary(self, ctx:TrinoParser.ArithmeticBinaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#arithmeticUnary.
    def visitArithmeticUnary(self, ctx:TrinoParser.ArithmeticUnaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#atTimeZone.
    def visitAtTimeZone(self, ctx:TrinoParser.AtTimeZoneContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#dereference.
    def visitDereference(self, ctx:TrinoParser.DereferenceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#typeConstructor.
    def visitTypeConstructor(self, ctx:TrinoParser.TypeConstructorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#jsonValue.
    def visitJsonValue(self, ctx:TrinoParser.JsonValueContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#specialDateTimeFunction.
    def visitSpecialDateTimeFunction(self, ctx:TrinoParser.SpecialDateTimeFunctionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#substring.
    def visitSubstring(self, ctx:TrinoParser.SubstringContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#cast.
    def visitCast(self, ctx:TrinoParser.CastContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#lambda.
    def visitLambda(self, ctx:TrinoParser.LambdaContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#parenthesizedExpression.
    def visitParenthesizedExpression(self, ctx:TrinoParser.ParenthesizedExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#trim.
    def visitTrim(self, ctx:TrinoParser.TrimContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#parameter.
    def visitParameter(self, ctx:TrinoParser.ParameterContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#normalize.
    def visitNormalize(self, ctx:TrinoParser.NormalizeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#jsonObject.
    def visitJsonObject(self, ctx:TrinoParser.JsonObjectContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#intervalLiteral.
    def visitIntervalLiteral(self, ctx:TrinoParser.IntervalLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#numericLiteral.
    def visitNumericLiteral(self, ctx:TrinoParser.NumericLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#booleanLiteral.
    def visitBooleanLiteral(self, ctx:TrinoParser.BooleanLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#jsonArray.
    def visitJsonArray(self, ctx:TrinoParser.JsonArrayContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#simpleCase.
    def visitSimpleCase(self, ctx:TrinoParser.SimpleCaseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#columnReference.
    def visitColumnReference(self, ctx:TrinoParser.ColumnReferenceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#nullLiteral.
    def visitNullLiteral(self, ctx:TrinoParser.NullLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#rowConstructor.
    def visitRowConstructor(self, ctx:TrinoParser.RowConstructorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#subscript.
    def visitSubscript(self, ctx:TrinoParser.SubscriptContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#jsonExists.
    def visitJsonExists(self, ctx:TrinoParser.JsonExistsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#currentPath.
    def visitCurrentPath(self, ctx:TrinoParser.CurrentPathContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#subqueryExpression.
    def visitSubqueryExpression(self, ctx:TrinoParser.SubqueryExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#binaryLiteral.
    def visitBinaryLiteral(self, ctx:TrinoParser.BinaryLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#currentUser.
    def visitCurrentUser(self, ctx:TrinoParser.CurrentUserContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#jsonQuery.
    def visitJsonQuery(self, ctx:TrinoParser.JsonQueryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#measure.
    def visitMeasure(self, ctx:TrinoParser.MeasureContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#extract.
    def visitExtract(self, ctx:TrinoParser.ExtractContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#stringLiteral.
    def visitStringLiteral(self, ctx:TrinoParser.StringLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#arrayConstructor.
    def visitArrayConstructor(self, ctx:TrinoParser.ArrayConstructorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#functionCall.
    def visitFunctionCall(self, ctx:TrinoParser.FunctionCallContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#currentSchema.
    def visitCurrentSchema(self, ctx:TrinoParser.CurrentSchemaContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#exists.
    def visitExists(self, ctx:TrinoParser.ExistsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#position.
    def visitPosition(self, ctx:TrinoParser.PositionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#listagg.
    def visitListagg(self, ctx:TrinoParser.ListaggContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#searchedCase.
    def visitSearchedCase(self, ctx:TrinoParser.SearchedCaseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#currentCatalog.
    def visitCurrentCatalog(self, ctx:TrinoParser.CurrentCatalogContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#groupingOperation.
    def visitGroupingOperation(self, ctx:TrinoParser.GroupingOperationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#jsonPathInvocation.
    def visitJsonPathInvocation(self, ctx:TrinoParser.JsonPathInvocationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#jsonValueExpression.
    def visitJsonValueExpression(self, ctx:TrinoParser.JsonValueExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#jsonRepresentation.
    def visitJsonRepresentation(self, ctx:TrinoParser.JsonRepresentationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#jsonArgument.
    def visitJsonArgument(self, ctx:TrinoParser.JsonArgumentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#jsonExistsErrorBehavior.
    def visitJsonExistsErrorBehavior(self, ctx:TrinoParser.JsonExistsErrorBehaviorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#jsonValueBehavior.
    def visitJsonValueBehavior(self, ctx:TrinoParser.JsonValueBehaviorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#jsonQueryWrapperBehavior.
    def visitJsonQueryWrapperBehavior(self, ctx:TrinoParser.JsonQueryWrapperBehaviorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#jsonQueryBehavior.
    def visitJsonQueryBehavior(self, ctx:TrinoParser.JsonQueryBehaviorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#jsonObjectMember.
    def visitJsonObjectMember(self, ctx:TrinoParser.JsonObjectMemberContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#processingMode.
    def visitProcessingMode(self, ctx:TrinoParser.ProcessingModeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#nullTreatment.
    def visitNullTreatment(self, ctx:TrinoParser.NullTreatmentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#basicStringLiteral.
    def visitBasicStringLiteral(self, ctx:TrinoParser.BasicStringLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#unicodeStringLiteral.
    def visitUnicodeStringLiteral(self, ctx:TrinoParser.UnicodeStringLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#timeZoneInterval.
    def visitTimeZoneInterval(self, ctx:TrinoParser.TimeZoneIntervalContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#timeZoneString.
    def visitTimeZoneString(self, ctx:TrinoParser.TimeZoneStringContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#comparisonOperator.
    def visitComparisonOperator(self, ctx:TrinoParser.ComparisonOperatorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#comparisonQuantifier.
    def visitComparisonQuantifier(self, ctx:TrinoParser.ComparisonQuantifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#booleanValue.
    def visitBooleanValue(self, ctx:TrinoParser.BooleanValueContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#interval.
    def visitInterval(self, ctx:TrinoParser.IntervalContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#intervalField.
    def visitIntervalField(self, ctx:TrinoParser.IntervalFieldContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#normalForm.
    def visitNormalForm(self, ctx:TrinoParser.NormalFormContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#rowType.
    def visitRowType(self, ctx:TrinoParser.RowTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#intervalType.
    def visitIntervalType(self, ctx:TrinoParser.IntervalTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#arrayType.
    def visitArrayType(self, ctx:TrinoParser.ArrayTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#doublePrecisionType.
    def visitDoublePrecisionType(self, ctx:TrinoParser.DoublePrecisionTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#legacyArrayType.
    def visitLegacyArrayType(self, ctx:TrinoParser.LegacyArrayTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#genericType.
    def visitGenericType(self, ctx:TrinoParser.GenericTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#dateTimeType.
    def visitDateTimeType(self, ctx:TrinoParser.DateTimeTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#legacyMapType.
    def visitLegacyMapType(self, ctx:TrinoParser.LegacyMapTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#rowField.
    def visitRowField(self, ctx:TrinoParser.RowFieldContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#typeParameter.
    def visitTypeParameter(self, ctx:TrinoParser.TypeParameterContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#whenClause.
    def visitWhenClause(self, ctx:TrinoParser.WhenClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#filter.
    def visitFilter(self, ctx:TrinoParser.FilterContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#mergeUpdate.
    def visitMergeUpdate(self, ctx:TrinoParser.MergeUpdateContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#mergeDelete.
    def visitMergeDelete(self, ctx:TrinoParser.MergeDeleteContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#mergeInsert.
    def visitMergeInsert(self, ctx:TrinoParser.MergeInsertContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#over.
    def visitOver(self, ctx:TrinoParser.OverContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#windowFrame.
    def visitWindowFrame(self, ctx:TrinoParser.WindowFrameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#frameExtent.
    def visitFrameExtent(self, ctx:TrinoParser.FrameExtentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#unboundedFrame.
    def visitUnboundedFrame(self, ctx:TrinoParser.UnboundedFrameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#currentRowBound.
    def visitCurrentRowBound(self, ctx:TrinoParser.CurrentRowBoundContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#boundedFrame.
    def visitBoundedFrame(self, ctx:TrinoParser.BoundedFrameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#quantifiedPrimary.
    def visitQuantifiedPrimary(self, ctx:TrinoParser.QuantifiedPrimaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#patternConcatenation.
    def visitPatternConcatenation(self, ctx:TrinoParser.PatternConcatenationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#patternAlternation.
    def visitPatternAlternation(self, ctx:TrinoParser.PatternAlternationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#patternVariable.
    def visitPatternVariable(self, ctx:TrinoParser.PatternVariableContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#emptyPattern.
    def visitEmptyPattern(self, ctx:TrinoParser.EmptyPatternContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#patternPermutation.
    def visitPatternPermutation(self, ctx:TrinoParser.PatternPermutationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#groupedPattern.
    def visitGroupedPattern(self, ctx:TrinoParser.GroupedPatternContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#partitionStartAnchor.
    def visitPartitionStartAnchor(self, ctx:TrinoParser.PartitionStartAnchorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#partitionEndAnchor.
    def visitPartitionEndAnchor(self, ctx:TrinoParser.PartitionEndAnchorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#excludedPattern.
    def visitExcludedPattern(self, ctx:TrinoParser.ExcludedPatternContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#zeroOrMoreQuantifier.
    def visitZeroOrMoreQuantifier(self, ctx:TrinoParser.ZeroOrMoreQuantifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#oneOrMoreQuantifier.
    def visitOneOrMoreQuantifier(self, ctx:TrinoParser.OneOrMoreQuantifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#zeroOrOneQuantifier.
    def visitZeroOrOneQuantifier(self, ctx:TrinoParser.ZeroOrOneQuantifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#rangeQuantifier.
    def visitRangeQuantifier(self, ctx:TrinoParser.RangeQuantifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#updateAssignment.
    def visitUpdateAssignment(self, ctx:TrinoParser.UpdateAssignmentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#explainFormat.
    def visitExplainFormat(self, ctx:TrinoParser.ExplainFormatContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#explainType.
    def visitExplainType(self, ctx:TrinoParser.ExplainTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#isolationLevel.
    def visitIsolationLevel(self, ctx:TrinoParser.IsolationLevelContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#transactionAccessMode.
    def visitTransactionAccessMode(self, ctx:TrinoParser.TransactionAccessModeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#readUncommitted.
    def visitReadUncommitted(self, ctx:TrinoParser.ReadUncommittedContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#readCommitted.
    def visitReadCommitted(self, ctx:TrinoParser.ReadCommittedContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#repeatableRead.
    def visitRepeatableRead(self, ctx:TrinoParser.RepeatableReadContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#serializable.
    def visitSerializable(self, ctx:TrinoParser.SerializableContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#positionalArgument.
    def visitPositionalArgument(self, ctx:TrinoParser.PositionalArgumentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#namedArgument.
    def visitNamedArgument(self, ctx:TrinoParser.NamedArgumentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#qualifiedArgument.
    def visitQualifiedArgument(self, ctx:TrinoParser.QualifiedArgumentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#unqualifiedArgument.
    def visitUnqualifiedArgument(self, ctx:TrinoParser.UnqualifiedArgumentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#pathSpecification.
    def visitPathSpecification(self, ctx:TrinoParser.PathSpecificationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#functionSpecification.
    def visitFunctionSpecification(self, ctx:TrinoParser.FunctionSpecificationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#functionDeclaration.
    def visitFunctionDeclaration(self, ctx:TrinoParser.FunctionDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#parameterDeclaration.
    def visitParameterDeclaration(self, ctx:TrinoParser.ParameterDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#returnsClause.
    def visitReturnsClause(self, ctx:TrinoParser.ReturnsClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#languageCharacteristic.
    def visitLanguageCharacteristic(self, ctx:TrinoParser.LanguageCharacteristicContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#deterministicCharacteristic.
    def visitDeterministicCharacteristic(self, ctx:TrinoParser.DeterministicCharacteristicContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#returnsNullOnNullInputCharacteristic.
    def visitReturnsNullOnNullInputCharacteristic(self, ctx:TrinoParser.ReturnsNullOnNullInputCharacteristicContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#calledOnNullInputCharacteristic.
    def visitCalledOnNullInputCharacteristic(self, ctx:TrinoParser.CalledOnNullInputCharacteristicContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#securityCharacteristic.
    def visitSecurityCharacteristic(self, ctx:TrinoParser.SecurityCharacteristicContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#commentCharacteristic.
    def visitCommentCharacteristic(self, ctx:TrinoParser.CommentCharacteristicContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#returnStatement.
    def visitReturnStatement(self, ctx:TrinoParser.ReturnStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#assignmentStatement.
    def visitAssignmentStatement(self, ctx:TrinoParser.AssignmentStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#simpleCaseStatement.
    def visitSimpleCaseStatement(self, ctx:TrinoParser.SimpleCaseStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#searchedCaseStatement.
    def visitSearchedCaseStatement(self, ctx:TrinoParser.SearchedCaseStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#ifStatement.
    def visitIfStatement(self, ctx:TrinoParser.IfStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#iterateStatement.
    def visitIterateStatement(self, ctx:TrinoParser.IterateStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#leaveStatement.
    def visitLeaveStatement(self, ctx:TrinoParser.LeaveStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#compoundStatement.
    def visitCompoundStatement(self, ctx:TrinoParser.CompoundStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#loopStatement.
    def visitLoopStatement(self, ctx:TrinoParser.LoopStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#whileStatement.
    def visitWhileStatement(self, ctx:TrinoParser.WhileStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#repeatStatement.
    def visitRepeatStatement(self, ctx:TrinoParser.RepeatStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#caseStatementWhenClause.
    def visitCaseStatementWhenClause(self, ctx:TrinoParser.CaseStatementWhenClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#elseIfClause.
    def visitElseIfClause(self, ctx:TrinoParser.ElseIfClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#elseClause.
    def visitElseClause(self, ctx:TrinoParser.ElseClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#variableDeclaration.
    def visitVariableDeclaration(self, ctx:TrinoParser.VariableDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#sqlStatementList.
    def visitSqlStatementList(self, ctx:TrinoParser.SqlStatementListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#privilege.
    def visitPrivilege(self, ctx:TrinoParser.PrivilegeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#qualifiedName.
    def visitQualifiedName(self, ctx:TrinoParser.QualifiedNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#queryPeriod.
    def visitQueryPeriod(self, ctx:TrinoParser.QueryPeriodContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#rangeType.
    def visitRangeType(self, ctx:TrinoParser.RangeTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#specifiedPrincipal.
    def visitSpecifiedPrincipal(self, ctx:TrinoParser.SpecifiedPrincipalContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#currentUserGrantor.
    def visitCurrentUserGrantor(self, ctx:TrinoParser.CurrentUserGrantorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#currentRoleGrantor.
    def visitCurrentRoleGrantor(self, ctx:TrinoParser.CurrentRoleGrantorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#unspecifiedPrincipal.
    def visitUnspecifiedPrincipal(self, ctx:TrinoParser.UnspecifiedPrincipalContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#userPrincipal.
    def visitUserPrincipal(self, ctx:TrinoParser.UserPrincipalContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#rolePrincipal.
    def visitRolePrincipal(self, ctx:TrinoParser.RolePrincipalContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#roles.
    def visitRoles(self, ctx:TrinoParser.RolesContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#unquotedIdentifier.
    def visitUnquotedIdentifier(self, ctx:TrinoParser.UnquotedIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#quotedIdentifier.
    def visitQuotedIdentifier(self, ctx:TrinoParser.QuotedIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#backQuotedIdentifier.
    def visitBackQuotedIdentifier(self, ctx:TrinoParser.BackQuotedIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#digitIdentifier.
    def visitDigitIdentifier(self, ctx:TrinoParser.DigitIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#decimalLiteral.
    def visitDecimalLiteral(self, ctx:TrinoParser.DecimalLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#doubleLiteral.
    def visitDoubleLiteral(self, ctx:TrinoParser.DoubleLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#integerLiteral.
    def visitIntegerLiteral(self, ctx:TrinoParser.IntegerLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#identifierUser.
    def visitIdentifierUser(self, ctx:TrinoParser.IdentifierUserContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#stringUser.
    def visitStringUser(self, ctx:TrinoParser.StringUserContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TrinoParser#nonReserved.
    def visitNonReserved(self, ctx:TrinoParser.NonReservedContext):
        return self.visitChildren(ctx)



del TrinoParser