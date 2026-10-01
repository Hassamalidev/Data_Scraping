import { relations } from "drizzle-orm/relations";
import { sources, listings, businesses, scrapeRuns, removalRequests, listingClaims, fieldProvenance } from "./schema";

export const listingsRelations = relations(listings, ({one, many}) => ({
	source: one(sources, {
		fields: [listings.sourceId],
		references: [sources.id]
	}),
	business: one(businesses, {
		fields: [listings.businessId],
		references: [businesses.id]
	}),
	fieldProvenances: many(fieldProvenance),
}));

export const sourcesRelations = relations(sources, ({many}) => ({
	listings: many(listings),
	scrapeRuns: many(scrapeRuns),
}));

export const businessesRelations = relations(businesses, ({many}) => ({
	listings: many(listings),
	removalRequests: many(removalRequests),
	listingClaims: many(listingClaims),
	fieldProvenances: many(fieldProvenance),
}));

export const scrapeRunsRelations = relations(scrapeRuns, ({one}) => ({
	source: one(sources, {
		fields: [scrapeRuns.sourceId],
		references: [sources.id]
	}),
}));

export const removalRequestsRelations = relations(removalRequests, ({one}) => ({
	business: one(businesses, {
		fields: [removalRequests.businessId],
		references: [businesses.id]
	}),
}));

export const listingClaimsRelations = relations(listingClaims, ({one}) => ({
	business: one(businesses, {
		fields: [listingClaims.businessId],
		references: [businesses.id]
	}),
}));

export const fieldProvenanceRelations = relations(fieldProvenance, ({one}) => ({
	business: one(businesses, {
		fields: [fieldProvenance.businessId],
		references: [businesses.id]
	}),
	listing: one(listings, {
		fields: [fieldProvenance.listingId],
		references: [listings.id]
	}),
}));