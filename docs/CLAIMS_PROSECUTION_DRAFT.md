# Revised claim set (prosecution draft, for patent-agent review)

Responds to `SIMULATED_FER.md`. No new matter: every feature is in `PATENT_TECHNICAL_DISCLOSURE.md` and the
reference implementation. No measured numbers are claimed.

## Definitions used in the claims (to be mirrored in the description)
"fidelity levels" — an ordered set of representations of an information object, F0 (full, including raw
evidence) to F4 (regional), where a higher index has fewer fields. "invariant value" — the value obtained by
applying a predetermined extraction function to a representation, including: location rounded to a stated
coordinate precision; observation time quantised to a stated interval; a categorical or bucketed field; a
geographic cell identifier; and a sketch key derived from an observation key. "duplicate-insensitive sketch" —
a fixed-size array of registers updated by a hash of an observation key such that re-inserting the same key
leaves it unchanged, merged by register-wise maximum.

## Independent claim 1 (node method)
1. A method of managing emergency information at a battery-powered node of a disruption-tolerant wireless
network, the node comprising a radio, a storage and a battery, the method comprising:
(a) forming, from a human report or a sensor reading, an information object comprising an event type, an
    observation key, a fidelity level of an ordered set of fidelity levels, and a payload;
(b) determining a resource pressure of the node from at least an occupancy of the storage and at least one of
    a remaining charge of the battery, a bandwidth available at the radio, an expected contact duration and an
    arrival rate of objects;
(c) determining a utility of the object from at least a criticality of its event type and an age of the
    observation, and determining from the utility and the resource pressure a proposed fidelity level, a
    higher pressure and a lower utility yielding a less complete level;
(d) generating a candidate representation of the object at the proposed level;
(e) for each invariant listed for the event type in a stored, versioned invariant registry, applying the
    invariant's extraction function to the candidate and to the object;
(f) committing the candidate only if (i) the proposed level is not less complete than a minimum fidelity level
    stored for the event type and (ii) each extracted value from the candidate is present and equal to the
    extracted value from the object, and otherwise committing the least complete representation, between the
    object's level and the proposed level, that satisfies (i) and (ii);
(g) storing a committed representation of an object of a protected event type as an individually addressable
    record in a protected store from which records are not evicted, and inserting the sketch key of a
    committed representation of an object of an aggregatable event type into a duplicate-insensitive sketch
    selected by event type, geographic cell and time window, wherein for an aggregatable event type the
    registry lists an invariant whose extraction function returns a value only for a representation carrying
    a sketch key, such that aggregation into a non-duplicate-insensitive counter is not committed; and
(h) upon a contact with a peer node, transmitting within a byte budget of the contact protected records in an
    order of decreasing utility and sketches whose registers differ, and merging received records by retaining,
    per record identifier, all versions that are maximal under an order of (logical time, fidelity level), and
    received sketches by register-wise maximum.

## Dependent claims
2. Claim 1, wherein the extraction functions comprise location rounded to approximately 1e-4 degree and
   observation time quantised to a fixed interval, and the protected event types comprise a trapped-person
   event requiring trapped status, location and freshness, and a medication-need event requiring label,
   urgency and location.
3. Claim 1, wherein a structural-risk event type is aggregatable when its risk state is low and protected with
   a less permissive minimum fidelity when its risk state is elevated or high.
4. Claim 1, wherein sensor objects comprise water-level, smoke-density and structural-vibration objects whose
   payload comprises a bucket of the measured value, and the registry lists the bucket, the geographic cell and
   the freshness as invariants.
5. Claim 4, wherein a sensor publishes objects at a period multiplied by a factor determined from the
   resource pressure and publishes immediately when the bucket changes.
6. Claim 4, wherein a sensor maintains a fixed-length ring buffer of raw samples and, upon a rising bucket or a
   transition to high structural risk, freezes the ring buffer as evidence and computes an integrity
   commitment over it.
7. Claim 1, wherein raw evidence of an object is sealed in an evidence store that is not merged at contacts,
   and the committed representation carries an evidence locator and the integrity commitment.
8. Claim 7, further comprising transferring the sealed evidence to up to a configured number of peer nodes,
   preferentially mobile peer nodes.
9. Claim 8, further comprising, after loss of the node at which the evidence originated, a responder node
   issuing an authorisation-bearing recovery request that is relayed at contacts, a peer node holding the
   sealed evidence verifying the authorisation and returning it, and the responder node accepting it only if
   an authentication tag, the integrity commitment and the locator are all verified, and thereupon storing
   the object at the most complete fidelity level.
10. Claim 1, wherein versions of one record identifier that are concurrently maximal with different content
    are all retained and reported as a conflict.
11. Claim 1, wherein the offered identifiers at a contact are limited to those changed since the last contact
    with the same peer.
12. Claim 1, wherein the registry carries a version identifier and a candidate with a different version
    identifier or event type is not committed.

## Independent claim 13 (promotion; depends on the state of claim 1 to preserve unity)
13. The method of claim 1, further comprising maintaining, per event type, geographic cell and time window, a
further duplicate-insensitive sketch of reporting-device identifiers, and evaluating at the node a
deterministic rule that is satisfied for a geographic cell when (i) an estimate from the union of the sketches
over retained windows reaches a first threshold, (ii) an estimate over a most-recent number of windows divided
by that number reaches a second threshold, (iii) a confidence computed from at least the device-sketch estimate
reaches a third threshold, and (iv) the latest window containing data is within a freshness limit; and, when
satisfied, creating a derived object of a protected event type whose record identifier is a deterministic
function of only the rule and the geographic cell, and storing it in the protected store, whereby replayed
copies of an observation do not change the estimates and nodes evaluating the rule on merged state create the
same record identifier.
14. Claim 13, wherein the rule maps water-request objects to a water-shortage event and smoke-density objects in
    elevated buckets to a potential-fire-cluster event.
15. Claim 13, wherein the confidence further comprises an estimate of distinct ingest nodes.
16. Claim 13, further comprising requesting evidence of objects in the geographic cell upon creation of the
    derived object.

## Claims with optional learned advisors (each includes its deterministic gate)
17. Claim 13, further comprising receiving from a trained model a proposed adjustment of the first threshold for
    a cell and replacing the first threshold by the base threshold plus the adjustment clamped to a fixed range
    relative to the base threshold, quantised to a fixed step and not below a floor, wherein only the rule of
    claim 13 creates derived objects.
18. Claim 1, further comprising receiving from a trained model a probability that a new aggregatable object
    duplicates an earlier object and inserting the earlier object's sketch key instead of the new key only if
    the probability exceeds a fixed value, the objects are of the same aggregatable event type and geographic
    cell, and their distance and time difference are within fixed limits, such that the model can only
    reduce an estimate.
19. Claim 1, further comprising receiving from a trained model a proposal to preserve an additional field
    in a reduced representation and adding at most a fixed number of bytes of that field only if a proposal
    score exceeds a fixed value, the representation with the added field being subject to step (f).

## Apparatus / medium
20. A node of a disruption-tolerant wireless network comprising a radio, a storage, a battery and a processor
    configured to perform the method of any of claims 1–19.
21. A system comprising a plurality of nodes according to claim 20 including at least one sensor node, at least
    one mobile node and at least one responder node.
22. A non-transitory computer-readable medium storing instructions that, when executed by a processor of a
    node, cause the node to perform the method of any of claims 1–19.
