import { pgTable, text, integer, boolean, timestamp, foreignKey, unique, uuid, jsonb, index, check, char, doublePrecision, date, numeric, primaryKey, pgEnum } from "drizzle-orm/pg-core"
import { sql } from "drizzle-orm"

export const businessStatus = pgEnum("business_status", ['active', 'possibly_closed', 'closed'])
export const halalStatus = pgEnum("halal_status", ['certified', 'certification_lapsed', 'self_declared', 'community_tagged', 'unknown'])
export const ownershipStatus = pgEnum("ownership_status", ['self_identified', 'not_stated'])
export const runStatus = pgEnum("run_status", ['queued', 'running', 'succeeded', 'partial', 'failed'])
export const sourceType = pgEnum("source_type", ['certifier', 'community_directory', 'open_data'])


export const sources = pgTable("sources", {
	id: text().primaryKey().notNull(),
	name: text().notNull(),
	type: sourceType().notNull(),
	baseUrl: text("base_url").notNull(),
	trustRank: integer("trust_rank").notNull(),
	intervalHours: integer("interval_hours").default(24).notNull(),
	enabled: boolean().default(true).notNull(),
	termsNotes: text("terms_notes"),
	attribution: text(),
	robotsCheckedAt: timestamp("robots_checked_at", { withTimezone: true, mode: 'string' }),
});

export const listings = pgTable("listings", {
	id: uuid().defaultRandom().primaryKey().notNull(),
	sourceId: text("source_id").notNull(),
	sourceRecordKey: text("source_record_key").notNull(),
	sourceUrl: text("source_url").notNull(),
	businessId: uuid("business_id"),
	raw: jsonb().notNull(),
	contentHash: text("content_hash").notNull(),
	firstSeenAt: timestamp("first_seen_at", { withTimezone: true, mode: 'string' }).defaultNow().notNull(),
	lastSeenAt: timestamp("last_seen_at", { withTimezone: true, mode: 'string' }).defaultNow().notNull(),
	missingRuns: integer("missing_runs").default(0).notNull(),
}, (table) => [
	foreignKey({
			columns: [table.sourceId],
			foreignColumns: [sources.id],
			name: "listings_source_id_fkey"
		}),
	foreignKey({
			columns: [table.businessId],
			foreignColumns: [businesses.id],
			name: "listings_business_id_fkey"
		}).onDelete("set null"),
	unique("listings_source_id_source_record_key_key").on(table.sourceId, table.sourceRecordKey),
]);

export const businesses = pgTable("businesses", {
	id: uuid().defaultRandom().primaryKey().notNull(),
	name: text().notNull(),
	nameNormalized: text("name_normalized").notNull(),
	category: text().notNull(),
	subcategory: text(),
	addressLine: text("address_line"),
	city: text(),
	province: char({ length: 2 }),
	postalCode: text("postal_code"),
	latitude: doublePrecision(),
	longitude: doublePrecision(),
	phoneE164: text("phone_e164"),
	website: text(),
	email: text(),
	halalStatus: halalStatus("halal_status").default('unknown').notNull(),
	certifier: text(),
	certificationExpires: date("certification_expires"),
	muslimOwned: ownershipStatus("muslim_owned").default('not_stated').notNull(),
	ownershipEvidenceUrl: text("ownership_evidence_url"),
	status: businessStatus().default('active').notNull(),
	confidence: numeric({ precision: 3, scale:  2 }).default('0.50').notNull(),
	claimed: boolean().default(false).notNull(),
	hidden: boolean().default(false).notNull(),
	firstSeenAt: timestamp("first_seen_at", { withTimezone: true, mode: 'string' }).defaultNow().notNull(),
	lastSeenAt: timestamp("last_seen_at", { withTimezone: true, mode: 'string' }).defaultNow().notNull(),
	lastVerifiedAt: timestamp("last_verified_at", { withTimezone: true, mode: 'string' }),
	updatedAt: timestamp("updated_at", { withTimezone: true, mode: 'string' }).defaultNow().notNull(),
}, (table) => [
	index("businesses_category_idx").using("btree", table.category.asc().nullsLast().op("text_ops")),
	index("businesses_halal_status_idx").using("btree", table.halalStatus.asc().nullsLast().op("enum_ops")),
	index("businesses_muslim_owned_idx").using("btree", table.muslimOwned.asc().nullsLast().op("enum_ops")),
	index("businesses_name_trgm").using("gin", table.nameNormalized.asc().nullsLast().op("gin_trgm_ops")),
	index("businesses_province_city_idx").using("btree", table.province.asc().nullsLast().op("bpchar_ops"), table.city.asc().nullsLast().op("bpchar_ops")),
	check("businesses_province_check", sql`province = ANY (ARRAY['AB'::bpchar, 'BC'::bpchar, 'MB'::bpchar, 'NB'::bpchar, 'NL'::bpchar, 'NS'::bpchar, 'NT'::bpchar, 'NU'::bpchar, 'ON'::bpchar, 'PE'::bpchar, 'QC'::bpchar, 'SK'::bpchar, 'YT'::bpchar])`),
	check("businesses_postal_code_check", sql`postal_code ~ '^[A-Z][0-9][A-Z] [0-9][A-Z][0-9]$'::text`),
]);

export const scrapeRuns = pgTable("scrape_runs", {
	id: uuid().defaultRandom().primaryKey().notNull(),
	sourceId: text("source_id").notNull(),
	status: runStatus().default('queued').notNull(),
	triggeredBy: text("triggered_by").default('schedule').notNull(),
	startedAt: timestamp("started_at", { withTimezone: true, mode: 'string' }),
	finishedAt: timestamp("finished_at", { withTimezone: true, mode: 'string' }),
	pagesFetched: integer("pages_fetched").default(0).notNull(),
	recordsNew: integer("records_new").default(0).notNull(),
	recordsUpdated: integer("records_updated").default(0).notNull(),
	recordsUnchanged: integer("records_unchanged").default(0).notNull(),
	recordsMissing: integer("records_missing").default(0).notNull(),
	errors: jsonb().default([]).notNull(),
}, (table) => [
	foreignKey({
			columns: [table.sourceId],
			foreignColumns: [sources.id],
			name: "scrape_runs_source_id_fkey"
		}),
]);

export const geocodeCache = pgTable("geocode_cache", {
	query: text().primaryKey().notNull(),
	latitude: doublePrecision(),
	longitude: doublePrecision(),
	provider: text().notNull(),
	raw: jsonb(),
	createdAt: timestamp("created_at", { withTimezone: true, mode: 'string' }).defaultNow().notNull(),
});

export const reviewQueue = pgTable("review_queue", {
	id: uuid().defaultRandom().primaryKey().notNull(),
	kind: text().notNull(),
	payload: jsonb().notNull(),
	status: text().default('open').notNull(),
	createdAt: timestamp("created_at", { withTimezone: true, mode: 'string' }).defaultNow().notNull(),
	resolvedAt: timestamp("resolved_at", { withTimezone: true, mode: 'string' }),
});

export const removalRequests = pgTable("removal_requests", {
	id: uuid().defaultRandom().primaryKey().notNull(),
	businessId: uuid("business_id"),
	contact: text().notNull(),
	reason: text(),
	status: text().default('open').notNull(),
	createdAt: timestamp("created_at", { withTimezone: true, mode: 'string' }).defaultNow().notNull(),
}, (table) => [
	foreignKey({
			columns: [table.businessId],
			foreignColumns: [businesses.id],
			name: "removal_requests_business_id_fkey"
		}).onDelete("cascade"),
]);

export const listingClaims = pgTable("listing_claims", {
	id: uuid().defaultRandom().primaryKey().notNull(),
	businessId: uuid("business_id").notNull(),
	ownerName: text("owner_name").notNull(),
	ownerEmail: text("owner_email").notNull(),
	publicOwner: boolean("public_owner").default(false).notNull(),
	selfIdentifiesMuslimOwned: boolean("self_identifies_muslim_owned").notNull(),
	consentText: text("consent_text").notNull(),
	verified: boolean().default(false).notNull(),
	createdAt: timestamp("created_at", { withTimezone: true, mode: 'string' }).defaultNow().notNull(),
}, (table) => [
	foreignKey({
			columns: [table.businessId],
			foreignColumns: [businesses.id],
			name: "listing_claims_business_id_fkey"
		}).onDelete("cascade"),
]);

export const fieldProvenance = pgTable("field_provenance", {
	businessId: uuid("business_id").notNull(),
	field: text().notNull(),
	value: text(),
	listingId: uuid("listing_id").notNull(),
	observedAt: timestamp("observed_at", { withTimezone: true, mode: 'string' }).defaultNow().notNull(),
}, (table) => [
	foreignKey({
			columns: [table.businessId],
			foreignColumns: [businesses.id],
			name: "field_provenance_business_id_fkey"
		}).onDelete("cascade"),
	foreignKey({
			columns: [table.listingId],
			foreignColumns: [listings.id],
			name: "field_provenance_listing_id_fkey"
		}).onDelete("cascade"),
	primaryKey({ columns: [table.businessId, table.field, table.listingId], name: "field_provenance_pkey"}),
]);
