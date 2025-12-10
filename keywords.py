"""Plain keyword lists for Nesta mission-aligned horizon scanning."""

from __future__ import annotations
from typing import Dict, List


def _keywords(block: str) -> List[str]:
    """Return unique, ordered keywords from a newline-separated block."""
    seen = []
    for line in block.strip().splitlines():
        term = line.strip()
        if not term:
            continue
        if term not in seen:
            seen.append(term)
    return seen


MISSION_KEYWORDS: Dict[str, List[str]] = {
    "A Sustainable Future": _keywords(
        """
        bioenergy
        biomass boiler
        biomass heat
        decarbon, build
        decarbon, built
        decarbon, built environment
        decarbon, home
        decarbon, house
        low carbon, build
        low carbon, built
        low carbon, built environment
        low carbon, home
        low carbon, house
        carbon capture
        carbon capture, storage
        climate tech
        green tech
        net zero material
        sustainability
        great british energy
        gb energy
        district, heat
        heat network
        energy efficiency, build
        energy efficiency, built
        energy efficiency, home
        energy efficiency, house
        energy management
        insulation, build
        insulation, home
        insulation, house
        retrofit
        smart meter
        smart thermostat
        demand response
        electricity grid
        energy grid
        batteries
        energy storage
        geothermal, energy
        geothermal, heat
        green skills
        heat pump
        heat pumps
        heat batteries
        heat battery
        heat storage
        thermal energy storage
        thermal storage
        blue hydrogen
        fuel cell, hydrogen
        gray hydrogen
        green hydrogen
        grey hydrogen
        hydrogen, energy
        hydrogen, boiler
        hydrogen, heat
        micro chp
        micro combined heat and power
        micro-chp
        micro-combined heat and power
        renewable energy
        photovoltaic
        solar energy
        solar panel
        solar thermal
        wind energy
        wind farm
        wind turbine
        """
    ),
    "A Fairer Start": _keywords(
        """
        curricula
        curriculum
        education content
        education resource
        education, material
        baby sitter
        baby sitters
        baby sitting
        babysitter
        babysitters
        babysitting
        child care
        child minder
        childcare
        childminder
        nannies
        nanny
        nurseries
        nursery
        nursery group
        nursery groups
        alternate school
        alternate schools
        kindergarten
        montessori
        pre school
        pre schools
        cognition
        cognitive
        executive function
        memory
        problem-solving
        communication
        language acquisition
        language development
        speech
        speech and language therapy
        speech therapy
        comprehension
        ebook
        handwriting
        letters
        literacy
        phonics
        read
        reading
        math
        mathematics
        maths
        numeracy
        games
        play
        playing
        toys
        learning through play
        game-based learning
        babies
        baby
        boy
        child
        childhood
        children
        daughter
        early learning
        early year
        early years
        edtech
        parent
        parents
        girl
        infant
        ~kid~
        ~kids~
        pre k
        toddler
        underserved children
        caregiver
        caregivers
        family dynamics
        family support
        home learning environment
        parenting
        parenting advice
        parenting support
        budgeting
        cash
        family income
        finance
        fintech
        finances
        financial
        financial inclusion
        parent income
        back to work
        employment
        parent, employment
        parent, job
        parent, work
        parental leave
        work-life balance
        community involvement
        community support
        peer
        peer group
        peer support
        peer to peer
        social network
        analytics
        classroom tech
        classroom technology
        digital learning environment
        management
        monitoring technology
        occupancy
        operations
        waitlist
        waitlists
        ~art~
        ~arts~
        drawing
        music
        painting
        singing
        song
        songs
        infancy
        newborn
        motor skills
        physical development
        spatial awareness
        bedtime routine
        sleep duration
        sleep pattern
        sleep quality
        adhd
        attention-deficit hyperactivity disorder
        autism
        disabilities
        dyslexia
        learning difficulties
        learning difficulty
        special needs
        spectrum disorder
        baby products
        baby food
        nutrition
        weight
        dietary habits
        breastfeeding
        obesity
        overweight
        malnutrition
        birth
        fetal development
        maternal health
        pregnancy
        prenatal development
        """
    ),
    "A Healthy Life": _keywords(
        """
        diet
        food
        food manufacture
        food manufacturing
        food process
        food processing
        food product
        food production
        food science
        food sector
        food service
        food studies
        food study
        food tech
        food technology
        groceries
        grocery
        kitchen
        meat
        nutrients
        nutrition
        obesity
        vegetable
        alt protein
        alternative protein
        dairy substitute
        seafood substitute
        cloud kitchen
        dark kitchen
        delivery-only kitchen
        ghost kitchen
        kitchen space rent
        virtual kitchen
        10 min delivery
        delivery app
        delivery platform
        delivery-only food brand
        food delivery
        grocery deliveries
        grocery delivery
        last mile delivery
        meal deliveries
        meal delivery
        ultra fast delivery
        biomass fermentation
        mycoprotein
        precision fermentation
        quorn
        healthy food
        age tech
        agetech
        health tech
        healthtech
        med tech
        medtech
        healthcare
        insect protein
        automated kitchen
        cooking tech
        cooking technology
        food preparation, technology
        intelligent appliance
        intelligent kitchen
        kitchen app
        kitchen automation
        kitchen device
        kitchen management software
        kitchen software
        kitchen tech
        kitchen technology
        kitchen, automation
        kitchen, internet of things
        kitchen, technology
        recipe app
        robot chef
        robot cook
        robot kitchen
        robot, kitchen
        robotic chef
        robotic cook
        robotic kitchen
        robotics, kitchen
        smart appliance
        smart kitchen
        artificial meat
        artificial protein
        cell-based meat
        cell-based protein
        clean meat
        cultivated meat
        cultivated protein
        cultured meat
        cultured protein
        fake meat
        in vitro meat
        in vitro protein
        lab-grown meat
        lab-grown protein
        no-kill meat
        slaughter-free meat
        synthetic meat
        synthetic protein
        loneliness
        lonely
        social isolation
        meal box
        meal kit
        recipe box
        subscription box
        mental health, digital
        mental health, tech
        diet personalisation
        diet personalization
        gut microbiome, diet
        nutrigenomics
        nutrition app
        nutrition personalisation
        nutrition personalization
        personalised diet
        personalised nutrition
        personalized diet
        personalized nutrition
        plant burger
        plant-based burger
        plant-based meat
        plant-based protein
        vegetable protein
        alternative emulsifier
        artificial fat
        artificial fatty acid
        fat mimetic
        fat replacement
        fat substitute
        fatty acid substitute
        low calorie fat
        low calorie, fat
        low calorie, fatty acid
        low fat
        dietary fiber
        dietary fibre
        fiber additive
        fibre additive
        high fiber
        high fibre
        ingredient, food
        low calorie
        low calorie density
        reformulated, food
        reformulation, food
        synthetic biology, food
        synthetic biology, nutrient
        synthetic biology, nutrition
        low salt
        reduced salt
        salt reduction
        artificial sugar
        artificial sweetener
        diet sugar
        low calorie sugar
        low calorie, sugar
        low sugar
        reduced sugar
        sugar free
        sugar reduction
        sugar substitute
        catering management software
        catering software
        catering tech
        catering technology
        catering, automated
        catering, automation
        catering, robot
        catering, robotics
        catering, software
        restaurant management software
        restaurant software
        restaurant tech
        restaurant technology
        restaurant, automated
        restaurant, automation
        restaurant, robot
        restaurant, robotics
        restaurant, software
        restaurant, technology
        restaurants, technology
        check-out, tech
        checkout, tech
        in-store management software
        in-store software
        in-store tech
        in-store technology
        in-store, automate
        in-store, automation
        in-store, robot
        in-store, robotics
        retail management software
        retail software
        retail tech
        retail technology
        retail, automate
        retail, automation
        retail, robot
        retail, robotics
        retail, software
        retail, technology
        supermarket tech
        supermarket technology
        supermarket, automate
        supermarket, automation
        supermarket, robot
        supermarket, robotics
        supermarket, software
        supermarket, tech
        cold chain
        fulfillment, automate
        fulfillment, automation
        fulfillment, robot
        picker robot
        picking, automate
        picking, automation
        picking, robot
        robot picker
        robotic picker
        supply chain, food
        warehouse, automate
        warehouse, automation
        warehouse, robot
        diabetes
        overweight
        weight loss
        glp-1
        obesity prevention
        neurogastroenterology
        marketing
        advertising
        advertisement
        advertisements
        promotion
        promotions
        branding
        brand
        influencer
        influencers
        audience
        audiences
        facebook
        instagram
        twitter
        tiktok
        youtube
        snapchat
        linkedin
        pinterest
        social media
        glp 1
        semaglutide
        ozempic
        wegovy
        mounjaro
        tirzepatide
        liraglutide
        dulaglutide
        glucagon-like peptide
        glucagon like peptide
        weight loss medication
        weight loss medicine
        weight loss drug
        retatrutide
        cagrisema
        amylin
        gip
        tri-agonist
        anti-obesity medication
        digital therapeutic
        digital therapeutics
        dtx
        software as a medical device
        samd
        digital medicine
        prescribed digital
        prescription digital
        health coaching
        digital coaching
        remote patient monitoring
        virtual care platform
        lifestyle change program
        behavioural therapy
        behavioral therapy
        nhs digital weight management
        pre-diabetes
        prediabetes
        type 2 diabetes
        metabolic health
        weight management
        low carb
        low fat
        no added sugar
        high protein
        protein rich
        alternative protein
        high fibre
        keto
        ketogenic
        plant-based
        plant-based diet
        vegan
        healthy snack
        functional food
        meal replacement
        diet shake
        meal shake
        nutritionally complete
        total diet replacement
        protein bar
        protein shake
        functional beverage
        health drink
        ready meal
        ready-to-eat meal
        physical activity
        exercise
        fitness
        workout
        training
        gym
        home gym
        sports tech
        connected fitness
        smart gym
        smart fitness
        interactive fitness
        virtual fitness
        online fitness
        peloton
        exergame
        exergaming
        gamified fitness
        fitness game
        sweetener
        sugar alternative
        sugar reduction
        allulose
        erythritol
        monk fruit
        stevia
        thaumatin
        tagatose
        fat replacer
        fat reduction
        oleogel
        structured lipids
        alternative fat
        low sodium
        potassium chloride
        sodium reduction
        fiber enhancement
        fibre enhancement
        fiber enhancer
        fibre enhancer
        hydrocolloid
        inulin
        chicory root fibre
        bulking agent
        texturant
        ingredient science
        food formulation
        clean label
        reformulation
        reformulated
        functional ingredient
        telehealth
        telemedicine
        online pharmacy
        digital clinic
        companion app
        patient support programme
        digital health
        wellness coaching
        medication adherence
        treatment adherence
        side effect management
        gas fermentation
        solid-state fermentation
        fungal protein
        mycelium
        cellular agriculture
        cultivated meat
        cultured meat
        lab-grown meat
        cell-based meat
        cultivated protein
        cultured protein
        lab-grown protein
        cell-based protein
        slaughter-free meat
        in vitro meat
        clean meat
        synthetic meat
        ai-driven discovery
        computational biology
        ingredient discovery platform
        food design
        ai ingredient
        synthetic biology
        novel food
        alt protein
        fitness tracker
        health tracker
        wearable device
        wearable technology
        smart scale
        smart scales
        smart watch
        wellness app
        health app
        calorie counter
        food diary
        food log
        weight loss app
        fitness app
        personal health
        health and wellness
        personalized nutrition
        personalised nutrition
        gut microbiome
        wellbeing
        well-being
        nutrition personalisation
        nutrition personalization
        personalised diet
        personalized diet
        nutrigenomics
        retail
        retailer
        supermarket
        grocery
        grocer
        cpg
        fmcg
        in-store
        checkout
        analytics
        insights
        data platform
        consumer data
        sales data
        basket analysis
        point of sale
        pos data
        business intelligence
        consumer intelligence
        nutritional data
        health trends
        food sales
        hfss
        shopper behaviour
        e-bike
        ebike
        e-scooter
        escooter
        electric bike
        electric scooter
        bicycle
        cycling
        walking
        micromobility
        micro-mobility
        bike sharing
        bike share
        scooter sharing
        scooter share
        bike subscription
        cycle to work
        active travel
        active transport
        urban mobility
        sustainable transport
        retail analytics
        shopper data
        loyalty data
        basket data
        retail data
        customer segmentation
        """
    ),
}


CROSS_CUTTING_KEYWORDS: List[str] = _keywords(
    """
    genetic factor
    genetic screening
    genetics
    heredity
    brain development
    brain imaging
    cognitive neuroscience
    neuroscience
    diagnostic tool
    non-technical assessment
    questionnaire
    survey
    randomised controlled trial
    colonialism
    cultural diversity
    diversity
    equality
    equity
    ethnicity
    inclusion
    multiculturalism
    race
    racism
    inequality
    social disparities
    child development policy
    early childhood education policy
    government policy
    policies
    policy
    social services
    support programs
    augmented reality
    immersive technology
    virtual reality
    data collection
    data platform
    database
    ai
    artificial intelligence
    computer vision
    convolutional neural network
    data analysis
    data science
    machine learning
    speech recognition
    digital literacy
    internet
    internet coverage
    internet usage
    online learning
    online safety
    media influence
    media literacy
    news media
    screen time
    app
    mobile device
    mobile learning
    tablet
    robot
    robotics
    facebook
    instagram
    online communities
    snapchat
    social media
    social networking
    tiktok
    smart watch
    wearable device
    wearable technology
    retention
    shift work
    shiftwork
    well being
    wellbeing
    wellness
    agencies
    agency
    recruitment
    talent
    talent aqcuisition
    apprenticeships
    development
    performance
    skill
    skills
    teacher training
    training
    """
)
