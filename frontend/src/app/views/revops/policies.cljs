(ns app.views.revops.policies
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [clojure.string :as str]
            [app.ds.layout :as layout]
            [app.ds.badge :as badge]
            [app.views.revops.policy-edit-modal :as edit-modal]
            [app.utils.format :as fmt]
            [app.auth.subs]))

;; -----------------------------------------------------------------------------
;; Operating-Theatre Ledger — overdrive layer
;;
;; The page never blocks. Counts roll, rows reposition, edits commit
;; optimistically, status changes flash. All inside the editorial-ledger laws.
;; -----------------------------------------------------------------------------

(def ^:const row-h 52)
(def ^:const overscan 8)
(def ^:const per-page 100)
(def ^:const flip-ms 520)
(def ^:const flash-ms 750)
(def ^:const saved-ms 950)

(defn- or-dash [v] (if (or (nil? v) (= v "")) "·" v))

(def benefit-labels
  {"SAUDE" "Saúde" "ODONTO" "Odonto" "VIDA" "Vida"})

(defn- fmt-benefit [v]
  (or (get benefit-labels v) v "·"))

(defn- fmt-date
  "ISO yyyy-mm-dd → dd/mm/yyyy."
  [iso]
  (if (and iso (string? iso) (>= (count iso) 10))
    (let [[y m d] (str/split (subs iso 0 10) #"-")]
      (str d "/" m "/" y))
    "·"))

(defn- request-params
  "Strip empty strings and request the current server page."
  [f page]
  (-> f
      (update :status #(when-not (= "" %) %))
      (update :search #(when-not (= "" %) %))
      (update :ev_id  #(when-not (= "" %) %))
      (assoc :per_page per-page)
      (assoc :page page)))

(defn- sort-glyph [active? order]
  (cond
    (and active? (= order "asc")) "↑"
    active?                       "↓"
    :else                         "↕"))

(defn- next-sort-order [filters field]
  (if (= field (:sort_by filters))
    (if (= "asc" (:sort_order filters)) "desc" "asc")
    "asc"))

(defn- sortable-head [{:keys [label field filters on-sort]}]
  (let [active? (= field (:sort_by @filters))
        order   (:sort_order @filters)]
    [:div.col.sortable
     {:role "columnheader"
      :tab-index 0
      :aria-sort (if active?
                   (if (= "asc" order) "ascending" "descending")
                   "none")
      :data-active (str active?)
      :title (str "Ordenar por " label)
      :on-click #(on-sort field)
      :on-key-down (fn [e]
                     (when (#{"Enter" " "} (.-key e))
                       (.preventDefault e)
                       (on-sort field)))}
     label
     [:span.sort-glyph {:aria-hidden true} (sort-glyph active? order)]]))

(defn- reduced-motion? []
  (boolean (some-> js/window
                   (.matchMedia "(prefers-reduced-motion: reduce)")
                   (.-matches))))

(defn- ease-out-quart [t] (- 1 (Math/pow (- 1 t) 4)))

(defn- tween-text!
  "Smoothly tween the element's textContent from its current integer value to
   the target. Falls back to an instant set when the tab is hidden or the user
   prefers reduced motion — keeps the displayed integer correct in any state."
  [el target]
  (when el
    (let [target  (long (or target 0))
          start   (or (some-> (.-textContent el) js/parseInt) 0)
          start   (if (js/isNaN start) 0 start)
          hidden? (.-hidden js/document)
          dur     (if (or (reduced-motion?) hidden?) 0 480)]
      (when-let [prev (aget el "__tweenRaf")]
        (js/cancelAnimationFrame prev)
        (aset el "__tweenRaf" nil))
      (cond
        (= start target) nil
        (zero? dur)      (set! (.-textContent el) (str target))
        :else
        (let [t0 (js/performance.now)
              step (fn step [now]
                     (let [t (min 1 (/ (- now t0) dur))
                           v (Math/round (+ start (* (- target start) (ease-out-quart t))))]
                       (set! (.-textContent el) (str v))
                       (if (< t 1)
                         (aset el "__tweenRaf" (js/requestAnimationFrame step))
                         (do (set! (.-textContent el) (str target))
                             (aset el "__tweenRaf" nil)))))]
          (aset el "__tweenRaf" (js/requestAnimationFrame step)))))))

(defn- parse-money
  "Accept '1234.56', '1.234,56', 'R$ 1234,56', or plain '1234'."
  [s]
  (when (string? s)
    (let [v (-> s
                str/trim
                (str/replace #"R\$" "")
                (str/replace #"\s" "")
                (str/replace #"\." "")
                (str/replace #"," "."))
          n (js/parseFloat v)]
      (when (and (number? n) (not (js/isNaN n)) (>= n 0))
        n))))

;; -----------------------------------------------------------------------------
;; count-chip — filter chip whose integer animates via @property
;; -----------------------------------------------------------------------------

(defn- count-chip [_props]
  (let [span-ref (atom nil)
        push! (fn [this]
                (tween-text! @span-ref (:tally (second (r/argv this)))))]
    (r/create-class
     {:display-name "policies/count-chip"
      :component-did-mount  push!
      :component-did-update (fn [this _] (push! this))
      :reagent-render
      (fn [{:keys [active? on-click label]}]
        [:button {:type "button"
                  :class (str "chip" (when active? " active"))
                  :aria-pressed (str (boolean active?))
                  :on-click on-click}
         label
         [:span.chip-count {:ref #(reset! span-ref %)}]])})))

(defn- detail-field
  ([label value] (detail-field label value nil))
  ([label value {:keys [wide?]}]
   [:div {:class (str "policy-detail-field" (when wide? " wide"))}
    [:span label]
    [:strong (or value "·")]]))

(defn- money-detail [label value]
  [detail-field label (or (fmt/fmt-brl-int value) "·")])

;; -----------------------------------------------------------------------------
;; Page
;; -----------------------------------------------------------------------------

(defn policies-page []
  (let [filters         (r/atom {:status "" :search "" :ev_id ""
                                 :sort_by "closed_date" :sort_order "desc"})
        page            (r/atom 1)
        modal-open?     (r/atom false)
        selected        (r/atom nil)
        focused-id      (r/atom nil)
        editing-cell    (r/atom nil)        ; {:id .. :field "total_paid_comissao"}
        edit-value      (r/atom "")
        scroll-y        (r/atom 0)
        viewport-h      (r/atom 600)
        flash-set       (r/atom #{})        ; ids whose status just changed
        saved-set       (r/atom #{})        ; ids whose row just persisted
        flip?           (r/atom false)      ; FLIP transition window
        prev-status     (atom nil)          ; non-reactive; for status-flash diffing
        viewport-ref    (atom nil)

        fetch-page! (fn [next-page]
                      (let [safe-page (max 1 next-page)]
                        (reset! page safe-page)
                        (reset! scroll-y 0)
                        (when-let [vp @viewport-ref]
                          (set! (.-scrollTop vp) 0))
                        (rf/dispatch [:revops/fetch-policies
                                      (request-params @filters safe-page)])))

        trigger-flip!
        (fn []
          (reset! flip? true)
          (js/setTimeout #(reset! flip? false) flip-ms))

        reset-fetch! (fn []
                       (fetch-page! 1))

        sort-by! (fn [field]
                   (trigger-flip!)
                   (swap! filters
                          (fn [f]
                            (assoc f
                                   :sort_by field
                                   :sort_order (next-sort-order f field))))
                   (reset-fetch!))

        scroll-into-view!
        (fn [id]
          (when-let [vp @viewport-ref]
            (let [policies (or @(rf/subscribe [:revops/policies]) [])
                  idx (->> policies
                           (map-indexed (fn [i p] (when (= (:id p) id) i)))
                           (some identity))]
              (when idx
                (let [target-top (* idx row-h)
                      cur-top (.-scrollTop vp)
                      vh (.-clientHeight vp)
                      cur-bottom (+ cur-top vh)]
                  (cond
                    (< target-top cur-top)
                    (set! (.-scrollTop vp) (max 0 (- target-top row-h)))

                    (> (+ target-top row-h) cur-bottom)
                    (set! (.-scrollTop vp) (- (+ target-top row-h) vh))

                    :else nil))))))

        focus-id!
        (fn [id]
          (reset! focused-id id)
          (when id (scroll-into-view! id)))

        save-cell!
        (fn [policy field-kw raw]
          (let [n (parse-money raw)]
            (when (and (some? n) (not= n (get policy field-kw)))
              (swap! saved-set conj (:id policy))
              (js/setTimeout #(swap! saved-set disj (:id policy)) saved-ms)
              (rf/dispatch [:revops/update-policy (:id policy) {field-kw n}])))
          (reset! editing-cell nil)
          (reset! edit-value ""))

        cancel-edit!
        (fn []
          (reset! editing-cell nil)
          (reset! edit-value ""))

        on-scroll
        (fn [e]
          (let [el (.-target e)]
            (reset! scroll-y (.-scrollTop el))))

        measure-viewport!
        (fn []
          (when-let [el @viewport-ref]
            (reset! viewport-h (.-clientHeight el))))

        on-resize (fn [_] (measure-viewport!))

        on-key
        (fn [e]
          (let [t (some-> (.-target e) .-tagName)
                editable? (or (= t "INPUT") (= t "TEXTAREA") (= t "SELECT"))]
            (when (and (not editable?) (not @modal-open?))
              (let [k (.-key e)
                    policies (or @(rf/subscribe [:revops/policies]) [])
                    ids (mapv :id policies)
                    cur-idx (when @focused-id
                              (->> ids
                                   (map-indexed (fn [i v] (when (= v @focused-id) i)))
                                   (some identity)))]
                (case k
                  ("j" "ArrowDown")
                  (do (.preventDefault e)
                      (when (seq ids)
                        (let [nxt (if (or (nil? cur-idx) (< cur-idx 0))
                                    0
                                    (min (dec (count ids)) (inc cur-idx)))]
                          (focus-id! (nth ids nxt nil)))))
                  ("k" "ArrowUp")
                  (do (.preventDefault e)
                      (when (seq ids)
                        (let [nxt (if (or (nil? cur-idx) (< cur-idx 0))
                                    0
                                    (max 0 (dec cur-idx)))]
                          (focus-id! (nth ids nxt nil)))))
                  "g"
                  (when (and (not (.-shiftKey e)) (not (.-ctrlKey e)) (not (.-metaKey e)))
                    (.preventDefault e)
                    (when-let [id (first ids)]
                      (focus-id! id)
                      (when-let [vp @viewport-ref]
                        (set! (.-scrollTop vp) 0))))
                  "G"
                  (do (.preventDefault e)
                      (when-let [id (last ids)]
                        (focus-id! id)))
                  "e"
                  (when (and @focused-id
                             (= "ADMIN" (:role @(rf/subscribe [:auth/current-user]))))
                    (.preventDefault e)
                    (when-let [row (some #(when (= (:id %) @focused-id) %) policies)]
                      (reset! selected row)
                      (reset! modal-open? true)))
                  "Escape"
                  (do (.preventDefault e)
                      (reset! focused-id nil))
                  nil)))))]

    (rf/dispatch [:revops/fetch-policies (request-params @filters @page)])
    (rf/dispatch [:revops/fetch-users])

    (r/create-class
     {:display-name "policies-page"

      :component-did-mount
      (fn [_]
        (measure-viewport!)
        (.addEventListener js/window "resize" on-resize)
        (.addEventListener js/window "keydown" on-key))

      :component-will-unmount
      (fn [_]
        (.removeEventListener js/window "resize" on-resize)
        (.removeEventListener js/window "keydown" on-key))

      :reagent-render
      (fn []
        (let [policies        (or @(rf/subscribe [:revops/policies]) [])
              meta            @(rf/subscribe [:revops/policies-meta])
              loading?        @(rf/subscribe [:revops/policies-loading?])
              users           @(rf/subscribe [:revops/users])
              user            @(rf/subscribe [:auth/current-user])
              editable?       (= "ADMIN" (:role user))
              route           @(rf/subscribe [:current-route-name])
              total-meta      (or (:total meta) (count policies))
              total-pages     (max 1 (or (:total_pages meta) 1))
              current-page    (min total-pages (max 1 (or (:page meta) @page)))
              in-validation   (count (filter #(= (:commission_status %) "IN_PAYMENT") policies))
              settled         (count (filter #(= (:commission_status %) "SETTLED") policies))
              suspended       (count (filter #(= (:commission_status %) "CANCELLED") policies))
              operators-count (count (->> policies (map :partner_operator) (filter some?) distinct))
              ev-options      (->> (or users [])
                                   (filter #(contains? #{"EV" "CN"} (:role %)))
                                   (sort-by #(or (:name %) (:email %))))
              detail-policy   (some #(when (= (:id %) @focused-id) %) policies)
              n               (count policies)
              total-h         (* n row-h)
              vh              @viewport-h
              y               @scroll-y
              first-idx       (max 0 (- (Math/floor (/ y row-h)) overscan))
              last-idx        (min n (+ (Math/ceil (/ (+ y vh) row-h)) overscan))
              visible         (if (zero? n)
                                []
                                (subvec (vec policies)
                                        (min n first-idx)
                                        (min n last-idx)))
              ;; Detect status changes for cyan flash. Ran as a side effect
              ;; during render, but deferred via queueMicrotask so it does not
              ;; mutate state inside the active render.
              _ (let [curr (into {} (map (juxt :id :commission_status) policies))
                      prev @prev-status]
                  (when (and prev (not= prev curr))
                    (let [changed (keep (fn [[id s]]
                                          (when (and (contains? prev id)
                                                     (not= s (get prev id)))
                                            id))
                                        curr)]
                      (when (seq changed)
                        (js/queueMicrotask
                         (fn []
                           (doseq [id changed]
                             (swap! flash-set conj id)
                             (js/setTimeout #(swap! flash-set disj id) flash-ms)))))))
                  (reset! prev-status curr))
              ;; Drop a focused-id that no longer exists in the dataset.
              _ (when (and @focused-id
                           (not (some #(= (:id %) @focused-id) policies)))
                  (js/queueMicrotask #(reset! focused-id nil)))]

          [layout/page-shell
           {:current-route route :user user
            :crumbs ["plataforma rv" "configuração" "apólices"]
            :title "Apólices"
            :subtitle (str total-meta " apólice" (when (not= 1 total-meta) "s")
                           (when (pos? operators-count)
                             (str " · " operators-count " operadora"
                                  (when (not= 1 operators-count) "s"))))}

           [:div.policies-overdrive
            ;; -------------------------------------------------------------
            ;; Filter chips (counts roll automatically) + EV select
            ;; -------------------------------------------------------------
            [:div.policies-controls
             [:div.policies-search
              [layout/icon "search" {:width 14 :height 14}]
              [:input {:placeholder "Apólice, cliente, EV..."
                       :aria-label "Buscar apólices"
                       :value (:search @filters)
                       :on-change (fn [e]
                                    (swap! filters assoc :search (.. e -target -value))
                                    (reset-fetch!))}]]
             [:div.policies-filterbar
              [:div.filter-row {:role "group" :aria-label "Filtrar por status"}
               [count-chip {:active? (= "" (:status @filters))
                            :tally   total-meta
                            :label   "Todas"
                            :on-click (fn []
                                        (trigger-flip!)
                                        (swap! filters assoc :status "")
                                        (reset-fetch!))}]
               [count-chip {:active? (= "IN_PAYMENT" (:status @filters))
                            :tally   in-validation
                            :label   "Em pagamento"
                            :on-click (fn []
                                        (trigger-flip!)
                                        (swap! filters assoc :status "IN_PAYMENT")
                                        (reset-fetch!))}]
               [count-chip {:active? (= "SETTLED" (:status @filters))
                            :tally   settled
                            :label   "Totalmente pagas"
                            :on-click (fn []
                                        (trigger-flip!)
                                        (swap! filters assoc :status "SETTLED")
                                        (reset-fetch!))}]
               [count-chip {:active? (= "CANCELLED" (:status @filters))
                            :tally   suspended
                            :label   "Canceladas"
                            :on-click (fn []
                                        (trigger-flip!)
                                        (swap! filters assoc :status "CANCELLED")
                                        (reset-fetch!))}]]
              [:div.policies-filter-meta
               [:select.period-select.ev-select
                {:value (:ev_id @filters)
                 :aria-label "Filtrar por EV"
                 :on-change (fn [e]
                              (trigger-flip!)
                              (swap! filters assoc :ev_id (.. e -target -value))
                              (reset-fetch!))}
                [:option {:value ""} "Todos os EVs"]
                (for [u ev-options]
                  ^{:key (:id u)}
                  [:option {:value (:id u)} (or (:name u) (:email u))])]]]]

            ;; -------------------------------------------------------------
            ;; Ledger — sticky head + virtual body
            ;; -------------------------------------------------------------
            [:div.policies-workspace {:data-detail-open (str (boolean detail-policy))}
             [:div.ledger
              [:div.ledger-head {:role "row"}
               [sortable-head {:label "Ticket ID"
                               :field "hubspot_ticket_id"
                               :filters filters
                               :on-sort sort-by!}]
               [sortable-head {:label "Apólice"
                               :field "numero_apolice"
                               :filters filters
                               :on-sort sort-by!}]
               [sortable-head {:label "EV"
                               :field "ev_name"
                               :filters filters
                               :on-sort sort-by!}]
               [sortable-head {:label "Cliente"
                               :field "client_name"
                               :filters filters
                               :on-sort sort-by!}]
               [sortable-head {:label "Operadora"
                               :field "partner_operator"
                               :filters filters
                               :on-sort sort-by!}]
               [sortable-head {:label "Benefício"
                               :field "benefit_type"
                               :filters filters
                               :on-sort sort-by!}]
               [sortable-head {:label "Data Gongo"
                               :field "closed_date"
                               :filters filters
                               :on-sort sort-by!}]
               [sortable-head {:label "Estado"
                               :field "commission_status"
                               :filters filters
                               :on-sort sort-by!}]]

              [:div.ledger-body
               {:ref #(do (reset! viewport-ref %) (when % (measure-viewport!)))
                :on-scroll on-scroll}
               (cond
                 (and loading? (zero? n))
                 [:div.ledger-state [:span.pulse] "carregando…"]

                 (zero? n)
                 [:div.ledger-state "nenhuma apólice encontrada"]

                 :else
                 [:div.ledger-spacer {:style {:height (str total-h "px")}}
                  [:div {:class (str "ledger-rows" (when @flip? " flip"))
                         :role "rowgroup"}
                   (for [[i p] (map-indexed vector visible)]
                     (let [idx (+ first-idx i)
                           id (:id p)
                           focused?    (= id @focused-id)
                           flashing?   (contains? @flash-set id)
                           saved?      (contains? @saved-set id)]
                       ^{:key (or id idx)}
                       [:div.ledger-row
                        {:role "row"
                         :tab-index 0
                         :aria-selected (str focused?)
                         :data-id id
                         :data-focused (str focused?)
                         :data-saved (str saved?)
                         :data-status-flash (str flashing?)
                         :style {:top (str (* idx row-h) "px")}
                         :on-click (fn [_] (reset! focused-id id))
                         :on-key-down (fn [e]
                                        (when (#{"Enter" " "} (.-key e))
                                          (.preventDefault e)
                                          (reset! focused-id id)))}
                        [:div.col.num.muted (or-dash (:hubspot_ticket_id p))]
                        [:div.col.name.num (or-dash (:numero_apolice p))]
                        [:div.col (or (:ev_name p) "·")]
                        [:div.col (or (:client_name p) "·")]
                        [:div.col.muted (or-dash (:partner_operator p))]
                        [:div.col.muted (fmt-benefit (:benefit_type p))]
                        [:div.col.num.muted (fmt-date (:closed_date p))]
                        [:div.col.estado
                         [badge/status-badge {:status (:commission_status p)}]]]))]])]

              (when (> total-pages 1)
                [:nav.ledger-pager {:aria-label "Paginação de apólices"}
                 [:div.ledger-page-meta {:aria-live "polite"}
                  (str "Página " current-page " de " total-pages
                       " · " total-meta " apólice"
                       (when (not= 1 total-meta) "s"))]
                 [:div.ledger-page-actions
                  [:button.ledger-page-btn
                   {:type "button"
                    :aria-label "Página anterior"
                    :disabled (<= current-page 1)
                    :on-click #(fetch-page! (dec current-page))}
                   [:span {:aria-hidden true} "‹"]
                   "Anterior"]
                  [:button.ledger-page-btn
                   {:type "button"
                    :aria-label "Próxima página"
                    :disabled (>= current-page total-pages)
                    :on-click #(fetch-page! (inc current-page))}
                   "Próxima"
                   [:span {:aria-hidden true} "›"]]]])]

             (when detail-policy
               [:aside.policy-detail {:aria-label "Detalhes da apólice"}
                [:div.policy-detail-head
                 [:div.policy-detail-title
                  [:span "apólice"]
                  [:h3 (or-dash (:numero_apolice detail-policy))]
                  [:p (str "Ticket " (or-dash (:hubspot_ticket_id detail-policy)))]]
                 [:button.policy-detail-close
                  {:type "button"
                   :on-click #(reset! focused-id nil)}
                  "Fechar"]]
                [:div.policy-detail-status
                 [badge/status-badge {:status (:commission_status detail-policy)}]]

                [:div.policy-detail-section
                 [:div.policy-detail-section-title "Financeiro"]
                 [:div.policy-detail-grid
                  [money-detail "MRR" (:mrr_for_commission detail-policy)]
                  [money-detail "Comissão potencial" (:commission_potential detail-policy)]
                  [money-detail "Total pago" (:total_pago detail-policy)]
                  [money-detail "Pago comissão" (:comissao_paga detail-policy)]
                  [money-detail "Pago agenciamento" (:agenciamento_pago detail-policy)]
                  [detail-field "Meses" (str (or (:installments_paid detail-policy) 0) "/12")]]]

                [:div.policy-detail-section
                 [:div.policy-detail-section-title "Origem"]
                 [:div.policy-detail-grid
                  [detail-field "Cliente" (or (:client_name detail-policy) "·") {:wide? true}]
                  [detail-field "EV" (or (:ev_name detail-policy) "·")]
                  [detail-field "Operadora" (or-dash (:partner_operator detail-policy))]
                  [detail-field "Benefício" (fmt-benefit (:benefit_type detail-policy))]
                  [detail-field "Data gongo" (fmt-date (:closed_date detail-policy))]]]

                (when editable?
                  [:div.policy-detail-actions
                   [:button.btn.btn-secondary.btn-sm
                    {:type "button"
                     :on-click (fn [_]
                                 (reset! selected detail-policy)
                                 (reset! modal-open? true))}
                    [layout/icon "edit" {:width 12 :height 12}]
                    "Editar apólice"]])])]

            (when editable?
              [edit-modal/policy-edit-modal
               {:open? @modal-open?
                :policy @selected
                :on-close #(reset! modal-open? false)}])]]))})))
